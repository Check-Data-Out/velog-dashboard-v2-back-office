import logging

from aiohttp.client import ClientSession
from aiohttp_retry import ExponentialRetry, RetryClient

from scraping.constants import (
    CURRENT_USER_QUERY,
    POSTS_STATS_QUERY,
    V2_CDN_URL,
    V3_URL,
    VELOG_POSTS_QUERY,
)

logger = logging.getLogger("scraping")


def get_header(access_token: str, refresh_token: str) -> dict[str, str]:
    return {
        "authority": "v3.velog.io",
        "origin": "https://velog.io",
        "content-type": "application/json",
        "cookie": f"access_token={access_token}; refresh_token={refresh_token}",
    }


async def fetch_velog_user_chk(
    session: ClientSession,
    access_token: str,
    refresh_token: str,
) -> tuple[dict[str, str], dict[str, str]]:
    # 토큰 유효성 검증
    payload = {"query": CURRENT_USER_QUERY}
    headers = get_header(access_token, refresh_token)
    try:
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
            return cookies, data
    except Exception as e:
        logger.error(f"Failed to fetch user: {e}")
        return {}, {}


async def fetch_velog_posts(
    session: ClientSession,
    username: str,
    access_token: str,
    refresh_token: str,
    cursor: str = "",
) -> list[dict[str, str]]:
    """한 유저의 포스트를 50개씩(최대 개수) 가져오는 함수"""
    query = VELOG_POSTS_QUERY
    variables = {
        "input": {
            "cursor": cursor,
            "username": f"{username}",
            "limit": 50,
            "tag": "",
        }
    }
    payload = {"query": query, "variables": variables}
    headers = get_header(access_token, refresh_token)

    try:
        async with session.post(
            V3_URL,
            json=payload,
            headers=headers,
        ) as response:
            data = await response.json()
            posts: list[dict[str, str]] = data["data"]["posts"]
            return posts
    except Exception as e:
        logger.error(f"Failed to fetch posts: {e} (username: {username})")
        return []


async def fetch_all_velog_posts(
    session: ClientSession,
    username: str,
    access_token: str,
    refresh_token: str,
) -> list[dict[str, str]]:
    """한 유저의 모든 포스트를 가져오는 함수"""
    cursor = ""
    total_posts = list()
    while True:
        posts = await fetch_velog_posts(
            session,
            username,
            access_token,
            refresh_token,
            cursor,
        )
        if not posts or "id" not in posts[-1]:
            break
        total_posts.extend(posts)
        cursor = posts[-1]["id"]
    return total_posts


async def fetch_post_stats(
    post_id: str,
    access_token: str,
    refresh_token: str,
) -> dict[str, str]:
    """post_id에 대한 통계 정보 가져오는 graphQL 호출"""

    query = POSTS_STATS_QUERY
    variables = {"post_id": post_id}
    payload = {
        "query": query,
        "variables": variables,
        "operationName": "GetStats",
    }
    headers = get_header(access_token, refresh_token)

    retry_options = ExponentialRetry(attempts=3, start_timeout=1)
    async with RetryClient(retry_options=retry_options) as retry_client:
        try:
            async with retry_client.post(
                V2_CDN_URL, json=payload, headers=headers
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(
                        f"HTTP error {response.status}: {text} (post_id: {post_id})"
                    )
                    return {}
                content_type = response.headers.get("Content-Type", "")
                if "application/json" not in content_type:
                    text = await response.text()
                    logger.error(
                        f"Unexpected response format: {text} (post_id: {post_id})"
                    )
                    return {}
                try:
                    res: dict[str, str] = await response.json()
                    return res
                except Exception as e:
                    logger.error(
                        f"JSON decoding failed: {e} (post_id: {post_id})"
                    )
                    return {}
        except Exception as e:
            logger.error(
                f"Failed to fetch post stats: {e} (post_id: {post_id})"
            )
            return {}
