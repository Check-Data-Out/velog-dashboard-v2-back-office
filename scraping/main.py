import asyncio

import aiohttp
import environ
import setup_django  # noqa

from modules.token_encryption.aes_encryption import AESEncryption
from scraping.constants.queries import CURRENT_USER_QUERY
from scraping.constants.urls import V3_URL
from users.models import User

env = environ.Env()


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


asyncio.run(main())
