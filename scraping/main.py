import asyncio
import logging

import aiohttp
import environ
from asgiref.sync import sync_to_async

from modules.token_encryption.aes_encryption import AESEncryption
from posts.models import Post, PostDailyStatistics
from scraping.apis import (
    fetch_all_velog_posts,
    fetch_post_stats,
    fetch_velog_user_chk,
)
from users.models import User
from utils.utils import get_local_now

logger = logging.getLogger("scraping")


class Scraper:
    def __init__(self, group_range: range, max_connections: int = 40):
        self.env = environ.Env()
        self.group_range = group_range
        # 최대 동시 연결 수 제한
        self.semaphore = asyncio.Semaphore(max_connections)

    async def update_old_tokens(
        self,
        user: User,
        aes_encryption: AESEncryption,
        new_user_cookies: dict[str, str],
    ) -> bool:
        """토큰 만료로 인한 토큰 업데이트"""
        current_access_token = aes_encryption.decrypt(user.access_token)
        current_refresh_token = aes_encryption.decrypt(user.refresh_token)
        try:
            # 복호화된 토큰과 새 토큰을 비교
            if new_user_cookies["access_token"] != current_access_token:
                user.access_token = aes_encryption.encrypt(
                    new_user_cookies["access_token"]
                )
            if new_user_cookies["refresh_token"] != current_refresh_token:
                user.refresh_token = aes_encryption.encrypt(
                    new_user_cookies["refresh_token"]
                )

            # 변경된 필드만 업데이트
            update_fields = []
            if new_user_cookies["access_token"] != current_access_token:
                update_fields.append("access_token")
            if new_user_cookies["refresh_token"] != current_refresh_token:
                update_fields.append("refresh_token")

            # 변경된 필드가 있을 때만 저장
            if update_fields:
                await user.asave(update_fields=update_fields)
                logger.info(f"Updated tokens for user {user.velog_uuid}")
                return True
        except Exception as e:
            logger.error(
                f"Failed to update tokens: {e}"
                f"(user velog uuid: {user.velog_uuid})"
            )
        finally:
            return False

    async def bulk_insert_posts(
        self,
        user: User,
        fetched_posts: list[dict[str, str]],
        batch_size: int = 200,
    ) -> bool:
        """Post 객체를 일정 크기의 배치로 나눠서 삽입"""
        try:
            for i in range(0, len(fetched_posts), batch_size):
                batch = [
                    Post(
                        post_uuid=post["id"],
                        title=post["title"],
                        user=user,
                        slug=post["url_slug"],
                        released_at=post["released_at"],
                    )
                    for post in fetched_posts[i : i + batch_size]
                ]
                bulk_create_sync = sync_to_async(
                    Post.objects.bulk_create, thread_sensitive=True
                )
                await bulk_create_sync(batch, ignore_conflicts=True)
            return True
        except Exception as e:
            logger.error(
                f"Failed to bulk create posts. {e}"
                f" (user velog uuid: {user.velog_uuid})"
            )
            return False

    async def update_daily_statistics(
        self, post: dict[str, str], stats: dict[str, str]
    ) -> None:
        """PostDailyStatistics를 업데이트 또는 생성 (upsert)"""
        if not stats or not isinstance(stats, dict):
            logger.warning(
                f"Skip updating statistics due to invalid stats data for post {post['id']}"
            )
            return

        try:
            post_obj = await sync_to_async(Post.objects.get)(
                post_uuid=post["id"]
            )
            today = get_local_now().date()

            stats_data = stats.get("data", {})  # type: ignore
            if not stats_data or not isinstance(
                stats_data.get("getStats"),  # type: ignore
                dict,
            ):
                logger.warning(
                    f"Skip updating statistics due to missing getStats data for post {post['id']}"
                )
                return

            view_count = stats_data["getStats"].get("total", 0)  # type: ignore
            like_count = post.get("likes", 0)

            (
                daily_stats,
                created,
            ) = await PostDailyStatistics.objects.aget_or_create(
                post=post_obj,
                date=today,
                defaults={
                    "daily_view_count": view_count,
                    "daily_like_count": like_count,
                },
            )
            if not created:
                daily_stats.daily_view_count = view_count
                daily_stats.daily_like_count = like_count
                daily_stats.updated_at = get_local_now()
                await daily_stats.asave(
                    update_fields=[
                        "daily_view_count",
                        "daily_like_count",
                        "updated_at",
                    ]
                )
        except Exception as e:
            logger.error(
                f"Failed to update daily statistics for post {post['id']}: {str(e)}"
            )
            return

    async def fetch_post_stats_limited(
        self,
        post_id: str,
        access_token: str,
        refresh_token: str,
    ) -> dict[str, str] | None:
        """세마포어를 적용한 fetch_post_stats"""
        async with self.semaphore:
            return await fetch_post_stats(post_id, access_token, refresh_token)

    async def process_user(
        self, user: User, session: aiohttp.ClientSession
    ) -> None:
        """스크레이핑 메인 비즈니스로직, 유저 데이터를 전체 처리"""
        aes_key_index = (user.group_id % 100) % 10
        aes_key = self.env(f"AES_KEY_{aes_key_index}").encode()
        aes_encryption = AESEncryption(aes_key)
        origin_access_token = aes_encryption.decrypt(user.access_token)
        origin_refresh_token = aes_encryption.decrypt(user.refresh_token)

        # 토큰 유효성 검증
        new_user_cookies, user_data = await fetch_velog_user_chk(
            session,
            origin_access_token,
            origin_refresh_token,
        )
        if not (user_data or new_user_cookies):
            return

        if user_data["data"]["currentUser"] is None:  # type: ignore
            logger.warning(
                f"Failed to fetch user data because of wrong tokens. (user velog uuid: {user.velog_uuid})"
            )
            return

        if new_user_cookies:
            await self.update_old_tokens(
                user,
                aes_encryption,
                new_user_cookies,
            )

        username = user_data["data"]["currentUser"]["username"]  # type: ignore
        fetched_posts = await fetch_all_velog_posts(
            session, username, origin_access_token, origin_refresh_token
        )

        await self.bulk_insert_posts(user, fetched_posts)

        # 게시물을 적절한 크기의 청크로 나누어 처리
        chunk_size = 40
        for i in range(0, len(fetched_posts), chunk_size):
            chunk_posts = fetched_posts[i : i + chunk_size]
            tasks = [
                self.fetch_post_stats_limited(
                    post["id"], origin_access_token, origin_refresh_token
                )
                for post in chunk_posts
            ]
            statistics_results = await asyncio.gather(*tasks)

            # 통계 정보 업데이트 처리
            update_tasks = []
            for post, stats in zip(chunk_posts, statistics_results):
                if stats:
                    update_tasks.append(
                        self.update_daily_statistics(post, stats)
                    )

            if update_tasks:
                await asyncio.gather(*update_tasks)

            # 선택적으로 처리 사이에 짧은 대기 시간 추가
            await asyncio.sleep(0.5)

        logger.info(
            f"Succeeded to update stats. (user velog uuid: {user.velog_uuid}, email: {user.email})"
        )

    async def run(self) -> None:
        """스크래핑 작업 실행"""
        logger.info(
            f"Start scraping velog posts and statistics for group range "
            f"({min(self.group_range)} ~ {max(self.group_range)}) \n"
            f"{get_local_now().isoformat()}"
        )
        users: list[User] = [
            user
            async for user in User.objects.filter(
                group_id__in=self.group_range
            )
        ]
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=30)
        ) as session:
            for user in users:
                await self.process_user(user, session)

        logger.info(
            f"Finished scraping for group range ({min(self.group_range)} ~ {max(self.group_range)})."
        )


class ScraperTargetUser(Scraper):
    def __init__(
        self, user_pk_list: list[int], max_connections: int = 40
    ) -> None:
        self.env = environ.Env()
        self.user_pk_list = user_pk_list
        # 최대 동시 연결 수 제한
        self.semaphore = asyncio.Semaphore(max_connections)

    async def run(self) -> None:
        """타겟 유저 스크래핑 작업 실행"""
        logger.info(
            f"Start target user scraping velog posts and statistics"
            f"({self.user_pk_list}) \n"
            f"{get_local_now().isoformat()}"
        )
        users: list[User] = [
            user
            async for user in User.objects.filter(id__in=self.user_pk_list)
        ]
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=30)
        ) as session:
            for user in users:
                await self.process_user(user, session)

        logger.info(f"Finished target user scraping ({self.user_pk_list}).")
