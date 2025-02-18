import argparse
import asyncio
import logging
import warnings
from datetime import datetime

import aiohttp
import environ
import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.utils import timezone

from modules.token_encryption.aes_encryption import AESEncryption
from posts.models import Post, PostDailyStatistics
from scraping.apis import (
    fetch_all_velog_posts,
    fetch_post_stats,
    fetch_velog_user_chk,
)
from users.models import User


class Scraper:
    def __init__(self, group_range: range):
        self.logger = logging.getLogger("scraping")
        self.env = environ.Env()
        self.group_range = group_range

    @staticmethod
    def get_local_now() -> datetime:
        """django timezone 을 기반으로 하는 실제 local의 now datetime"""
        utc_now = timezone.now()
        local_now: datetime = timezone.localtime(
            utc_now, timezone=timezone.get_current_timezone()
        )
        return local_now

    async def update_old_tokens(
        self,
        user: User,
        aes_encryption: AESEncryption,
        user_cookies: dict[str, str],
        origin_access_token: str,
        origin_refresh_token: str,
    ) -> None:
        """토큰 만료로 인한 토큰 업데이트"""
        response_access_token, response_refresh_token = (
            user_cookies["access_token"],
            user_cookies["refresh_token"],
        )
        if response_access_token != origin_access_token:
            user.access_token = aes_encryption.encrypt(response_access_token)
        if response_refresh_token != origin_refresh_token:
            user.refresh_token = aes_encryption.encrypt(response_refresh_token)

        try:
            await user.asave(update_fields=["access_token", "refresh_token"])
            self.logger.info(
                f"Succeeded to update tokens. (user velog uuid: {user.velog_uuid})"
            )
        except Exception as e:
            self.logger.error(
                f"Failed to update tokens. {e} (user velog uuid: {user.velog_uuid})"
            )

    async def bulk_create_posts(
        self, user: User, fetched_posts: list[dict[str, str]]
    ) -> bool:
        """Post 객체를 대량으로 생성"""
        try:
            await Post.objects.abulk_create(
                [
                    Post(
                        post_uuid=post["id"],
                        title=post["title"],
                        user=user,
                        slug=post["url_slug"],
                        released_at=post["released_at"],
                    )
                    for post in fetched_posts
                ],
                ignore_conflicts=True,
                batch_size=500,
            )
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to bulk create posts. {e} (user velog uuid: {user.velog_uuid})"
            )
            return False

    async def update_daily_statistics(
        self, post: dict[str, str], stats: dict[str, str]
    ) -> None:
        """PostDailyStatistics를 업데이트 또는 생성 (upsert)"""
        if not stats or not isinstance(stats, dict):
            self.logger.warning(
                f"Skip updating statistics due to invalid stats data for post {post['id']}"
            )
            return

        try:
            post_obj = await sync_to_async(Post.objects.get)(
                post_uuid=post["id"]
            )
            today = self.get_local_now().date()

            stats_data = stats.get("data", {})  # type: ignore
            if not stats_data or not isinstance(
                stats_data.get("getStats"),  # type: ignore
                dict,
            ):
                self.logger.warning(
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
                daily_stats.updated_at = self.get_local_now()
                await daily_stats.asave(
                    update_fields=[
                        "daily_view_count",
                        "daily_like_count",
                        "updated_at",
                    ]
                )
        except Exception as e:
            self.logger.error(
                f"Failed to update daily statistics for post {post['id']}: {str(e)}"
            )
            return

    async def process_user(
        self, user: User, session: aiohttp.ClientSession
    ) -> None:
        """유저 데이터를 처리"""
        aes_key_index = (user.group_id % 100) % 10
        aes_key = self.env(f"AES_KEY_{aes_key_index}").encode()
        aes_encryption = AESEncryption(aes_key)
        origin_access_token = aes_encryption.decrypt(user.access_token)
        origin_refresh_token = aes_encryption.decrypt(user.refresh_token)

        # 토큰 유효성 검증
        user_cookies, user_data = await fetch_velog_user_chk(
            session, origin_access_token, origin_refresh_token
        )
        if not (user_data or user_cookies):
            return

        if user_data["data"]["currentUser"] is None:  # type: ignore
            self.logger.warning(
                f"Failed to fetch user data because of wrong tokens. (user velog uuid: {user.velog_uuid})"
            )
            return

        if user_cookies:
            await self.update_old_tokens(
                user,
                aes_encryption,
                user_cookies,
                origin_access_token,
                origin_refresh_token,
            )

        username = user_data["data"]["currentUser"]["username"]  # type: ignore
        fetched_posts = await fetch_all_velog_posts(
            session, username, origin_access_token, origin_refresh_token
        )

        await self.bulk_create_posts(user, fetched_posts)

        tasks = [
            fetch_post_stats(
                post["id"], origin_access_token, origin_refresh_token
            )
            for post in fetched_posts
        ]
        statistics_results = await asyncio.gather(*tasks)

        for post, stats in zip(fetched_posts, statistics_results):
            if stats:
                await self.update_daily_statistics(post, stats)

        self.logger.info(
            f"Succeeded to update stats. (user velog uuid: {user.velog_uuid}, email: {user.email})"
        )

    async def run(self) -> None:
        """스크래핑 작업 실행"""
        self.logger.info(
            f"Start scraping velog posts and statistics for group range ({min(self.group_range)} ~ {max(self.group_range)})."
            f"{self.get_local_now().isoformat()}"
        )
        users: list[User] = [
            user
            async for user in User.objects.filter(
                group_id__in=self.group_range
            )
        ]
        async with aiohttp.ClientSession() as session:
            for user in users:
                await self.process_user(user, session)

        self.logger.info(
            f"Finished scraping for group range ({min(self.group_range)} ~ {max(self.group_range)})."
        )


def split_range(start: int, end: int, parts: int) -> list[range]:
    """주어진 범위를 지정된 수만큼 균등하게 분할"""
    width = end - start
    part_width = width // parts
    ranges = []

    for i in range(parts):
        part_start = start + (i * part_width)
        part_end = start + ((i + 1) * part_width) if i < parts - 1 else end
        ranges.append(range(part_start, part_end + 1))

    return ranges


async def main() -> None:
    """커맨드라인 인자를 파싱하고 그룹 범위를 3분할하여 처리"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-group",
        type=int,
        default=1,
        help="Minimum group number",
    )
    parser.add_argument(
        "--max-group",
        type=int,
        default=1000,
        help="Maximum group number",
    )
    args = parser.parse_args()

    group_ranges = split_range(args.min_group, args.max_group, 3)
    scrapers = [Scraper(group_range) for group_range in group_ranges]
    await asyncio.gather(*(scraper.run() for scraper in scrapers))


# Django에서 발생하는 RuntimeWarning 무시
warnings.filterwarnings(
    "ignore",
    message=r"DateTimeField .* received a naive datetime",
    category=RuntimeWarning,
)

# 실행
# TODO: Semaphore 로 asyncio.gather() 실행 제한 필요
# TODO: await asyncio.sleep(delay) 와 같은 사용자 사이 딜레이 있으면 velog 쪽에서 좋아할 듯
# TODO: return await asyncio.wait_for(task(*args), timeout=timeout) 와 같은 타임아웃이 필요
if __name__ == "__main__":
    asyncio.run(main())
