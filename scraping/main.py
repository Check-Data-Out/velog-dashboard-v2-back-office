import asyncio

import aiohttp
import environ
import setup_django  # noqa
from django.db import transaction

from modules.token_encryption.aes_encryption import AESEncryption
from posts.models import Post
from scraping.apis import fetch_velog_posts, fetch_velog_user_chk
from users.models import User

env = environ.Env()


async def update_old_tokens(
    user: User,
    aes_encryption: AESEncryption,
    user_cookies: dict[str, str],
    old_access_token: str,
    old_refresh_token: str,
) -> None:
    # 토큰 만료로 인한 토큰 업데이트
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
    await user.asave(update_fields=["access_token", "refresh_token"])


async def bulk_create_posts(
    user: User, fetched_posts: list[dict[str, str]]
) -> bool:
    existing_posts_id = [
        str(post.post_uuid)
        async for post in Post.objects.filter(user=user).aiterator()
    ]

    # 중복된 post 는 bulk_create 에 제외
    # TODO: 페이지네이션 감안해서 돌려야함
    new_posts = [
        fetched_post
        for fetched_post in fetched_posts
        if fetched_post["id"] not in existing_posts_id
    ]

    try:
        with transaction.atomic():
            await Post.objects.abulk_create(
                [
                    Post(
                        post_uuid=new_posts["id"],
                        title=new_posts["title"],
                        user=user,
                    )
                    for new_posts in new_posts
                ]
            )
    except Exception as e:
        # 에러 발생 시 롤백
        print("Error during bulk_create:", e)
        return False
    return True


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

            # 잘못된 토큰으로 인한 유저 정보 조회 불가
            if user_data["data"]["currentUser"] is None:  # type: ignore
                continue

            # 에러 상황임, 빈 값이면 안됨
            # TODO: 올바른 에러 처리 필요
            # if not user_cookies:
            #     continue

            # 토큰 만료로 인한 토큰 업데이트
            # TODO: return 값 을 기반으로 성공 실패 판단 해야함, 곧 에러처리로 이어짐
            # await update_old_tokens(
            #     user,
            #     aes_encryption,
            #     user_cookies,
            #     old_access_token,
            #     old_refresh_token,
            # )

            # username으로 velog post 조회
            # TODO: 페이지네이션 감안해서 돌려야함
            username = user_data["data"]["currentUser"]["username"]  # type: ignore
            fetched_posts = await fetch_velog_posts(
                session,
                username,
                old_access_token,
                old_refresh_token,
            )
            print(fetched_posts)

            # 새로운 post 저장
            await bulk_create_posts(user, fetched_posts)


asyncio.run(main())
