import asyncio
import logging
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

logger = logging.getLogger("scraping")

env = environ.Env()


def get_local_now() -> datetime:
    """django timezone 을 기반으로 하는 실제 local의 now datatime"""

    utc_now = timezone.now()
    local_now: datetime = timezone.localtime(
        utc_now,
        timezone=timezone.get_current_timezone(),
    )
    return local_now


async def update_old_tokens(
    user: User,
    aes_encryption: AESEncryption,
    user_cookies: dict[str, str],
    old_access_token: str,
    old_refresh_token: str,
) -> None:
    """토큰 만료로 인한 토큰 업데이트"""
    response_access_token, response_refresh_token = (
        user_cookies["access_token"],
        user_cookies["refresh_token"],
    )
    if response_access_token != old_access_token:
        new_access_token = aes_encryption.encrypt(response_access_token)
        user.access_token = new_access_token
    if response_refresh_token != old_refresh_token:
        new_refresh_token = aes_encryption.encrypt(response_refresh_token)
        user.refresh_token = new_refresh_token

    try:
        await user.asave(update_fields=["access_token", "refresh_token"])
        logger.info(
            f"Succeeded to update tokens. (user velog uuid: {user.velog_uuid})"
        )
    except Exception as e:
        logger.error(
            f"Failed to update tokens. {e} (user velog uuid: {user.velog_uuid})"
        )


async def bulk_create_posts(
    user: User, fetched_posts: list[dict[str, str]]
) -> bool:
    """post 를 bulk로 만드는 함수"""
    try:
        await Post.objects.abulk_create(
            [
                Post(
                    post_uuid=post["id"],
                    title=post["title"],
                    user=user,
                )
                for post in fetched_posts
            ],
            ignore_conflicts=True,
            batch_size=500,
        )
        return True
    except Exception as e:
        logger.error(
            f"Failed to bulk create posts. {e} (user velog uuid: {user.velog_uuid})"
        )
        return False


async def update_daily_statistics(
    post: dict[str, str], stats: dict[str, str]
) -> None:
    """PostDailyStatistics를 업데이트 또는 생성 (upsert)"""
    post_obj = await sync_to_async(Post.objects.get)(post_uuid=post["id"])
    today = get_local_now().date()
    daily_stats, created = await PostDailyStatistics.objects.aget_or_create(
        post=post_obj,
        date=today,
        defaults={
            "daily_view_count": stats["data"]["getStats"]["total"],  # type: ignore
            # TODO: like count 가져올 수 있어야 함
            "daily_like_count": stats.get("like_count", 0),
        },
    )
    if not created:
        # 기존 통계를 업데이트
        daily_stats.daily_view_count = stats["data"]["getStats"]["total"]  # type: ignore
        # TODO: like count 가져올 수 있어야 함
        daily_stats.daily_like_count = stats.get("like_count", 0)
        await daily_stats.asave(
            update_fields=["daily_view_count", "daily_like_count"]
        )


async def main() -> None:
    # TODO: group별 batch job 실행 방식 확정 후 리팩토링
    users: list[User] = [user async for user in User.objects.all()]
    async with aiohttp.ClientSession() as session:
        for user in users:
            encrypted_access_token = user.access_token
            encrypted_refresh_token = user.refresh_token

            # TODO: HARD_CODING 수정
            aes_key_index = (user.group_id % 100) % 10
            aes_key = env(f"AES_KEY_{aes_key_index}").encode()
            aes_encryption = AESEncryption(aes_key)
            old_access_token = aes_encryption.decrypt(encrypted_access_token)
            old_refresh_token = aes_encryption.decrypt(encrypted_refresh_token)

            # 토큰 유효성 검증
            user_cookies, user_data = await fetch_velog_user_chk(
                session,
                old_access_token,
                old_refresh_token,
            )

            # 유저 정보 조회 실패
            if not (user_data or user_cookies):
                continue

            # 잘못된 토큰으로 인한 유저 정보 조회 불가
            if user_data["data"]["currentUser"] is None:  # type: ignore
                logger.warning(
                    f"Failed to fetch user data because of wrong tokens. (user velog uuid: {user.velog_uuid})"
                )
                continue

            # 토큰 만료로 인한 토큰 업데이트
            if user_cookies:
                await update_old_tokens(
                    user,
                    aes_encryption,
                    user_cookies,
                    old_access_token,
                    old_refresh_token,
                )

            # username으로 velog post 조회
            username = user_data["data"]["currentUser"]["username"]  # type: ignore
            fetched_posts = await fetch_all_velog_posts(
                session,
                username,
                old_access_token,
                old_refresh_token,
            )

            # 새로운 post 저장
            await bulk_create_posts(user, fetched_posts)

            # 통계 API 호출 태스크 생성
            tasks = []
            for post in fetched_posts:
                tasks.append(
                    fetch_post_stats(
                        post["id"],
                        old_access_token,
                        old_refresh_token,
                    )
                )

            # 병렬 처리 (모든 통계 API 호출 수행)
            statistics_results = await asyncio.gather(*tasks)

            # PostDailyStatistics 업데이트
            for post, stats in zip(fetched_posts, statistics_results):
                if stats:  # 통계가 유효한 경우에만 업데이트
                    await update_daily_statistics(post, stats)


asyncio.run(main())
