# python manage.py shell 이후 아래 커멘드 기반 실행
"""
import threading
import asyncio
from modules.post_slug_update_batch import main  # main() 함수가 정의된 파일에서 import

def run_async_main():
    asyncio.run(main())

# 별도 스레드에서 실행
thread = threading.Thread(target=run_async_main)
thread.start()
thread.join()  # 스레드가 끝날 때까지 대기
"""

import asyncio

import aiohttp
import environ
from aiohttp.client import ClientSession
from asgiref.sync import sync_to_async

from modules.token_encryption.aes_encryption import AESEncryption
from posts.models import Post
from scraping.apis import fetch_all_velog_posts, fetch_velog_user_chk
from users.models import User

env = environ.Env()
KEYS = [
    "...",
]


async def update_user_posts(session: ClientSession, user: User) -> None:
    aes_key_index = (user.group_id % 100) % 10
    aes_key = env(f"AES_KEY_{aes_key_index}").encode()
    # aes_key = KEYS[(user.group_id % 100) % 10].encode()
    aes_encryption = AESEncryption(aes_key)
    access_token = aes_encryption.decrypt(user.access_token)
    refresh_token = aes_encryption.decrypt(user.refresh_token)

    _, user_data = await fetch_velog_user_chk(
        session, access_token, refresh_token
    )
    username = user_data["data"]["currentUser"]["username"]  # type: ignore
    fetched_posts = await fetch_all_velog_posts(
        session, username, access_token, refresh_token
    )

    for post in fetched_posts:
        try:
            target_post = await sync_to_async(Post.objects.get)(
                user=user,
                post_uuid=post["id"],
            )
            target_post.slug = post["url_slug"]
            await target_post.asave()
        except Post.DoesNotExist:
            continue


async def main() -> None:
    users = await sync_to_async(list)(User.objects.all())
    async with aiohttp.ClientSession() as session:
        tasks = [update_user_posts(session, user) for user in users]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
