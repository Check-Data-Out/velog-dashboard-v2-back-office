import logging
from typing import Any

from aiohttp.client import ClientSession

from scraping.constants import (
    CURRENT_USER_QUERY,
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
) -> tuple[dict[str, Any], dict[str, Any]]:
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
) -> list[dict[str, Any]]:
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
            posts: list[dict[str, Any]] = data["data"]["posts"]
            return posts
    except Exception as e:
        logger.error(f"Failed to fetch posts: {e} (username: {username})")
        return []


async def fetch_all_velog_posts(
    session: ClientSession,
    username: str,
    access_token: str,
    refresh_token: str,
) -> list[dict[str, Any]]:
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
