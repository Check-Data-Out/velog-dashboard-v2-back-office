import asyncio

import aiohttp
import environ
import setup_django  # noqa
from aiohttp.client import ClientSession

from modules.token_encryption.aes_encryption import AESEncryption
from posts.models import Post
from scraping.constants.queries import CURRENT_USER_QUERY, VELOG_POSTS_QUERY
from scraping.constants.urls import V3_URL
from users.models import User

env = environ.Env()


async def fetch_velog_posts(
    session: ClientSession,
    username: str,
    access_token: str,
    refresh_token: str,
) -> list[dict[str, str]]:
    query = VELOG_POSTS_QUERY
    variable = {
        "input": {
            "cursor": "",
            "username": f"{username}",
            "limit": 50,
            "tag": "",
        }
    }
    payload = {"query": query, "variables": variable}
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"access_token={access_token}; refresh_token={refresh_token};",
    }

    async with session.post(V3_URL, json=payload, headers=headers) as response:
        data = await response.json()
        print(data["data"]["posts"])
        posts: list[dict[str, str]] = data["data"]["posts"]

        return posts


# TODO: logging
async def main() -> None:
    # TODO: group별 batch job 실행 방식 확정 후 리팩토링
    users: list[User] = [user async for user in User.objects.all()]
    async with aiohttp.ClientSession() as session:
        for user in users:
            encrypted_access_token = user.access_token
            encrypted_refresh_token = user.refresh_token

            aes_key_index = (
                user.group_id % 100
            ) % 10  # TODO: HARD_CODING 수정
            aes_key = env(f"AES_KEY_{aes_key_index}").encode()
            aes_encryption = AESEncryption(aes_key)
            access_token = aes_encryption.decrypt(encrypted_access_token)
            refresh_token = aes_encryption.decrypt(encrypted_refresh_token)

            # 토큰 유효성 검증
            payload = {"query": CURRENT_USER_QUERY}
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"access_token={access_token}; refresh_token={refresh_token};",
            }

            async with session.post(
                V3_URL,
                json=payload,
                headers=headers,
            ) as response:
                data = await response.json()
                cookies = {
                    cookie.key: cookie.value
                    for cookie in response.cookies.values()
                }

                # 잘못된 토큰으로 인한 유저 정보 조회 불가
                if data["data"]["currentUser"] is None:
                    continue

                # 토큰 만료로 인한 토큰 업데이트
                if cookies:
                    response_access_token, response_refresh_token = (
                        cookies["access_token"],
                        cookies["refresh_token"],
                    )
                    if response_access_token != access_token:
                        access_token = aes_encryption.encrypt(
                            response_access_token
                        )
                        user.access_token = access_token
                    if response_refresh_token != refresh_token:
                        refresh_token = aes_encryption.encrypt(
                            response_refresh_token
                        )
                        user.refresh_token = refresh_token
                    await user.asave(
                        update_fields=["access_token", "refresh_token"]
                    )

            # username으로 velog post 조회
            username = data["data"]["currentUser"]["username"]
            fetched_posts = await fetch_velog_posts(
                session, username, access_token, refresh_token
            )

            # 새로운 post 저장
            existing_posts_id: list[str] = [
                str(post.post_uuid) async for post in user.posts.all()
            ]
            new_posts = [
                fetched_post
                for fetched_post in fetched_posts
                if fetched_post["id"] not in existing_posts_id
            ]
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


asyncio.run(main())
