import asyncio
import logging
from typing import Any

import aiohttp
import environ
import sentry_sdk
from asgiref.sync import sync_to_async
from django.db import transaction

from modules.token_encryption.aes_encryption import AESEncryption
from posts.models import Post, PostDailyStatistics
from scraping.apis import fetch_all_velog_posts, fetch_velog_user_chk
from scraping.constants import VELOG_HTTP_TIMEOUT
from users.models import User
from utils.utils import get_local_now

logger = logging.getLogger("scraping")


class TokenUpdateError(Exception):
    """토큰 갱신(DB 저장) 실패 — 원인은 ``__cause__`` 에 체인."""


class UserInfoUpdateError(Exception):
    """유저 정보 갱신(DB 저장) 실패 — 원인은 ``__cause__`` 에 체인."""


class Scraper:
    def __init__(self, group_range: range):
        self.env = environ.Env()
        self.group_range = group_range

    async def update_old_tokens(
        self,
        user: User,
        aes_encryption: AESEncryption,
        new_user_cookies: dict[str, str],
    ) -> bool:
        """토큰 만료로 인한 토큰 업데이트"""
        current_access_token = aes_encryption.decrypt(user.access_token)
        current_refresh_token = aes_encryption.decrypt(user.refresh_token)

        if current_access_token is None or current_refresh_token is None:
            return False

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
            # 상위(process_user → consumer 재시도)가 최종 1회만 보고하므로
            # 여기서는 capture 하지 않고 원인을 체인해 전파한다 (R5).
            logger.warning(
                f"Failed to update tokens: {e}"
                f"(user velog uuid: {user.velog_uuid})",
                exc_info=e,
            )
            raise TokenUpdateError(
                f"Failed to update tokens (user velog uuid: {user.velog_uuid})"
            ) from e
        return False

    async def update_old_user_info(
        self, user: User, user_data: dict[str, Any]
    ) -> bool:
        """사용자 프로필 정보 업데이트"""

        field_updates = {}

        # 각 필드별 업데이트 체크 및 적용
        if (new_email := user_data.get("email")) and (
            not user.email or user.email != new_email
        ):
            field_updates["email"] = new_email

        if (new_username := user_data.get("username")) and (
            not user.username or user.username != new_username
        ):
            field_updates["username"] = new_username

        if (profile := user_data.get("profile")) and (
            new_thumbnail := profile.get("thumbnail")
        ):
            if not user.thumbnail or user.thumbnail != new_thumbnail:
                field_updates["thumbnail"] = new_thumbnail

        # 업데이트할 필드가 없으면 조기 반환
        if not field_updates:
            return True

        try:
            # 필드 일괄 업데이트
            for field, value in field_updates.items():
                setattr(user, field, value)

            await user.asave(update_fields=list(field_updates.keys()))

            logger.info(
                "Updated user profile fields %s for %s",
                list(field_updates.keys()),
                user.velog_uuid,
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to update user info: %s (user velog uuid: %s)",
                e,
                user.velog_uuid,
                exc_info=e,
            )
            raise UserInfoUpdateError(
                f"Failed to update user_info (user velog uuid: {user.velog_uuid})"
            ) from e

    async def bulk_upsert_posts(
        self,
        user: User,
        fetched_posts: list[dict[str, Any]],
        batch_size: int = 200,
    ) -> bool:
        """Post 객체를 일정 크기의 배치로 나눠서 삽입 또는 업데이트"""
        try:
            for i in range(0, len(fetched_posts), batch_size):
                batch_posts = fetched_posts[i : i + batch_size]
                await self._upsert_batch(user, batch_posts)
                # 배치 작업 사이 강제 대기 시간
                await asyncio.sleep(0.2)
            return True
        except Exception as e:
            logger.error(
                f"Failed to bulk upsert posts. {e}"
                f" (user velog uuid: {user.velog_uuid})"
            )
            sentry_sdk.capture_exception(e)
            return False

    async def _upsert_batch(
        self, user: User, batch_posts: list[dict[str, Any]]
    ) -> None:
        """단일 배치 처리, bulk_upsert_posts 에서 호출됨"""

        @sync_to_async(thread_sensitive=True)  # type: ignore
        def _execute_transaction() -> None:
            with transaction.atomic():
                post_uuids = [post["id"] for post in batch_posts]
                existing_posts = {
                    str(post.post_uuid): post
                    for post in Post.objects.filter(post_uuid__in=post_uuids)
                }

                posts_to_create = []
                posts_to_update = []

                for post_data in batch_posts:
                    post_uuid = post_data["id"]
                    if post_uuid in existing_posts:
                        post = existing_posts[post_uuid]
                        post.title = post_data["title"]
                        post.slug = post_data["url_slug"]
                        post.released_at = post_data["released_at"]
                        posts_to_update.append(post)
                    else:
                        posts_to_create.append(
                            Post(
                                post_uuid=post_uuid,
                                title=post_data["title"],
                                user=user,
                                slug=post_data["url_slug"],
                                released_at=post_data["released_at"],
                            )
                        )

                if posts_to_update:
                    Post.objects.bulk_update(
                        posts_to_update, ["title", "slug", "released_at"]
                    )

                if posts_to_create:
                    Post.objects.bulk_create(posts_to_create)

        await _execute_transaction()

    async def sync_post_active_status(
        self,
        user: User,
        current_post_ids: set[str],
        min_posts_threshold: int = 1,
    ) -> None:
        """현재 API에서 가져온 게시글 목록을 기준으로 활성/비활성 상태 동기화

        Args:
            user: 대상 사용자
            current_post_ids: 현재 API에서 가져온 게시글 ID 집합
            min_posts_threshold: API 응답에 최소 이 개수 이상의 게시글이 있어야 상태변경을 실행
        """

        # API 응답이 너무 적으면 상태변경 하지 않음 (API 오류 가능성)
        if len(current_post_ids) < min_posts_threshold:
            logger.warning(
                f"Skipping post status sync for user {user.velog_uuid} - Too few posts returned ({len(current_post_ids)})"
            )
            return

        @sync_to_async(thread_sensitive=True)  # type: ignore
        def _execute_sync() -> None:
            # 1. 비활성화 로직: 현재 목록에 없는 활성화된 게시글 찾기
            posts_to_deactivate = Post.objects.filter(
                user=user, is_active=True
            ).exclude(post_uuid__in=current_post_ids)

            deactivation_count = posts_to_deactivate.count()

            # 너무 많은 게시글이 비활성화되는 경우 방어 로직
            active_posts_count = Post.objects.filter(
                user=user, is_active=True
            ).count()

            if (
                active_posts_count > 0
                and deactivation_count / active_posts_count > 0.5
            ):
                logger.warning(
                    f"Suspicious deactivation detected for user {user.velog_uuid}: "
                    f"Would deactivate {deactivation_count} out of {active_posts_count} posts. "
                    f"Skipping post status sync as a safety measure."
                )
                return

            # 2. 재활성화 로직: 현재 목록에 있지만 비활성화된 게시글 찾기
            posts_to_reactivate = Post.objects.filter(
                user=user, is_active=False, post_uuid__in=current_post_ids
            )

            reactivation_count = posts_to_reactivate.count()

            # 상태 업데이트 실행
            if deactivation_count > 0:
                logger.info(
                    f"Deactivating {deactivation_count} posts for user {user.velog_uuid}"
                )
                posts_to_deactivate.update(is_active=False)

            if reactivation_count > 0:
                logger.info(
                    f"Reactivating {reactivation_count} posts for user {user.velog_uuid}"
                )
                posts_to_reactivate.update(is_active=True)

        await _execute_sync()

    async def update_daily_statistics(
        self, post: dict[str, Any], view_count: int
    ) -> bool:
        """PostDailyStatistics를 업데이트 또는 생성 (upsert).

        실제로 기록했으면 True. 예외를 삼키므로 호출부가 성공 건수를
        셀 수 있도록 결과를 돌려준다.
        """
        try:
            today = get_local_now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            post_id = post["id"]

            like_count = post.get("likes", 0)

            # 트랜잭션 내에서 실행
            @sync_to_async  # type: ignore
            def update_stats_in_transaction() -> None:
                with transaction.atomic():
                    # 락을 최소화하기 위해 select_for_update는 사용하지 않음
                    try:
                        post_obj = Post.objects.get(post_uuid=post_id)

                        daily_stats, created = (
                            PostDailyStatistics.objects.get_or_create(
                                post=post_obj,
                                date=today,
                                defaults={
                                    "daily_view_count": view_count,
                                    "daily_like_count": like_count,
                                },
                            )
                        )

                        if not created:
                            daily_stats.daily_view_count = view_count
                            daily_stats.daily_like_count = like_count
                            daily_stats.updated_at = get_local_now()
                            daily_stats.save(
                                update_fields=[
                                    "daily_view_count",
                                    "daily_like_count",
                                    "updated_at",
                                ]
                            )
                    except Post.DoesNotExist as e:
                        logger.warning(f"Post not found: {post_id}")
                        sentry_sdk.capture_exception(e)
                        raise

            await update_stats_in_transaction()
            return True

        except Post.DoesNotExist:
            return False
        except Exception as e:
            logger.error(
                f"Failed to update daily statistics for post {post['id']}: {str(e)}"
            )
            sentry_sdk.capture_exception(e)
            return False

    async def process_user(
        self, user: User, session: aiohttp.ClientSession
    ) -> None:
        """스크레이핑 메인 비즈니스로직, 유저 데이터를 전체 처리"""
        aes_key_index = (user.group_id % 100) % 10
        aes_key = self.env(f"AES_KEY_{aes_key_index}").encode()
        aes_encryption = AESEncryption(aes_key)
        origin_access_token = aes_encryption.decrypt(user.access_token)
        origin_refresh_token = aes_encryption.decrypt(user.refresh_token)

        # ========================================================== #
        # STEP1: 토큰이 유효성 체크 및 업데이트. 이후 사용자 정보 업데이트
        # ========================================================== #

        # 토큰 유효성 검증
        new_user_cookies, user_data = await fetch_velog_user_chk(
            session,
            origin_access_token,
            origin_refresh_token,
        )

        if (
            not (user_data or new_user_cookies)
            or user_data.get("data", {}).get("currentUser") is None
        ):
            logger.warning(
                f"Failed to fetch user data because of wrong tokens. (user velog uuid: {user.velog_uuid})"
            )
            return

        if new_user_cookies:
            user_token_result = await self.update_old_tokens(
                user,
                aes_encryption,
                new_user_cookies,
            )
            if not user_token_result:
                raise TokenUpdateError(
                    "Failed to update tokens, Check the logs"
                )
            origin_access_token = new_user_cookies["access_token"]
            origin_refresh_token = new_user_cookies["refresh_token"]

        # velog 응답과 기존 저장된 사용자 정보 비교 및 업데이트
        # user_data -> currentUser 에는 id / username / email / profile { thumbnail } 존재
        user_info_result = await self.update_old_user_info(
            user,
            user_data["data"]["currentUser"],
        )
        if not user_info_result:
            raise UserInfoUpdateError(
                "Failed to update user_info, Check the logs"
            )

        # ========================================================== #
        # STEP2: 게시물 전체 목록을 가져와서 upsert 와 상태 동기화 (비활성, 활성)
        # ========================================================== #
        username = user_data["data"]["currentUser"]["username"]
        fetched_posts = await fetch_all_velog_posts(
            session, username, origin_access_token, origin_refresh_token
        )
        all_post_ids = {post["id"] for post in fetched_posts}
        logger.info(
            f"Fetched {len(all_post_ids)} posts for user {user.velog_uuid}"
        )

        # 게시물이 새로 생겼으면 추가, 아니면 업데이트
        await self.bulk_upsert_posts(user, fetched_posts)

        # 게시글 활성/비활성 상태 동기화
        await self.sync_post_active_status(
            user, all_post_ids, min_posts_threshold=1
        )

        # ========================================================== #
        # STEP3: STEP2 응답의 views 를 그대로 일별 통계로 upsert
        # ========================================================== #
        # 게시물을 적절한 크기의 청크로 나누어 처리
        chunk_size = 20
        succeeded = 0
        for i in range(0, len(fetched_posts), chunk_size):
            chunk_posts = fetched_posts[i : i + chunk_size]

            # views 가 없으면 건너뛴다. 0 으로 덮어쓰면 누적 스냅샷이
            # 급락하므로 truthiness 가 아니라 is not None 으로 판별한다.
            update_tasks = [
                self.update_daily_statistics(post, views)
                for post in chunk_posts
                if (views := post.get("views")) is not None
            ]

            if update_tasks:
                results = await asyncio.gather(*update_tasks)
                succeeded += sum(results)

            # 처리 사이에 짧은 대기 시간 추가
            await asyncio.sleep(0.5)

        failed = len(fetched_posts) - succeeded
        stats_summary = (
            f"succeeded={succeeded} failed={failed} "
            f"(user velog uuid: {user.velog_uuid}, email: {user.email})"
        )
        if failed and not succeeded:
            logger.error(f"Failed to update stats. {stats_summary}")
        elif failed:
            logger.warning(f"Partially updated stats. {stats_summary}")
        else:
            logger.info(f"Succeeded to update stats. {stats_summary}")

    async def process_users(
        self, users: list[User], session: aiohttp.ClientSession
    ) -> None:
        """유저 목록을 순회하며 처리한다.

        한 유저의 예외가 프로세스를 죽이면 그 그룹의 남은 유저가 통째로
        누락되므로 유저 단위로 격리한다. 유저가 한 명뿐인 온디맨드
        경로는 격리 이득이 없고 실패 신호만 잃으므로
        ScraperTargetUser 가 이 동작을 재정의한다.
        """
        for user in users:
            try:
                await self.process_user(user, session)
            except Exception as e:
                logger.error(
                    f"Failed to process user: {e} "
                    f"(user velog uuid: {user.velog_uuid})"
                )
                sentry_sdk.capture_exception(e)

    async def run(self) -> None:
        """스크래핑 작업 실행"""
        logger.info(
            f"Start scraping velog posts and statistics for group range "
            f"({min(self.group_range)} ~ {max(self.group_range)}) \n"
            f"{get_local_now().isoformat()}"
        )

        # [25.06.13] 핫픽스: 쿠키 자동 저장 강제 비활성화
        connector = aiohttp.TCPConnector(limit=30)
        cookie_jar = aiohttp.DummyCookieJar()  # 쿠키 저장 비활성화

        users = [
            user
            async for user in User.objects.filter(
                group_id__in=self.group_range
            )
        ]
        async with aiohttp.ClientSession(
            connector=connector,
            cookie_jar=cookie_jar,
            timeout=VELOG_HTTP_TIMEOUT,
        ) as session:
            await self.process_users(users, session)

        logger.info(
            f"Finished scraping for group range ({min(self.group_range)} ~ {max(self.group_range)})."
        )


class ScraperTargetUser(Scraper):
    def __init__(self, user_pk_list: list[int]) -> None:
        self.env = environ.Env()
        self.user_pk_list = user_pk_list

    async def process_users(
        self, users: list[User], session: aiohttp.ClientSession
    ) -> None:
        """예외를 그대로 전파한다.

        컨슈머(consumer/message_handler.py)가 예외 발생 여부로 재시도와
        DLQ 이동을 판정하므로, 삼키면 실패가 성공으로 보고된다.
        """
        for user in users:
            await self.process_user(user, session)

    async def run(self) -> None:
        """타겟 유저 스크래핑 작업 실행"""
        logger.info(
            f"Start target user scraping velog posts and statistics"
            f"({self.user_pk_list}) \n"
            f"{get_local_now().isoformat()}"
        )

        users = [
            user
            async for user in User.objects.filter(id__in=self.user_pk_list)
        ]
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=30),
            timeout=VELOG_HTTP_TIMEOUT,
        ) as session:
            await self.process_users(users, session)

        logger.info(f"Finished target user scraping ({self.user_pk_list}).")
