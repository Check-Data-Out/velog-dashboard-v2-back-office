import logging
from typing import Any

from aiohttp.client import ClientSession

from scraping.constants import (
    CURRENT_USER_QUERY,
    V3_URL,
    VELOG_POSTS_QUERY,
)
from scraping.reporting import SOURCE_VELOG_API, capture_scraper_failure

logger = logging.getLogger("scraping")


class VelogFetchError(Exception):
    """페이지 조회 실패 — 잘린 목록으로 진행하지 않도록 호출자에게 전파."""


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
        # 호출자는 빈 값으로 실패를 알 수 있으므로 로그는 warning, 이벤트는 1건.
        logger.warning(f"Failed to fetch user: {e}")
        capture_scraper_failure(e, source=SOURCE_VELOG_API)
        return {}, {}


async def fetch_velog_posts(
    session: ClientSession,
    username: str,
    access_token: str,
    refresh_token: str,
    cursor: str = "",
) -> list[dict[str, Any]]:
    """한 유저의 포스트를 50개씩(최대 개수) 가져오는 함수.

    Returns:
        포스트 목록. 빈 목록은 "더 없음"(정상).

    Raises:
        VelogFetchError: 네트워크/파싱 실패. 원인은 ``__cause__`` 에 체인.
    """
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
        # 보고는 최종 지점(consumer 재시도 소진 / 배치 유저 단위)에서 1회.
        # 원인은 __cause__ 로 전달돼 거기서 velog-api 원인별로 묶인다.
        logger.warning(f"Failed to fetch posts: {e} (username: {username})")
        raise VelogFetchError(
            f"Failed to fetch posts (username: {username}, cursor: {cursor!r})"
        ) from e


async def fetch_all_velog_posts(
    session: ClientSession,
    username: str,
    access_token: str,
    refresh_token: str,
) -> list[dict[str, Any]]:
    """한 유저의 모든 포스트를 가져오는 함수.

    Raises:
        VelogFetchError: 어느 페이지든 조회에 실패하면(fetch_velog_posts 가
            그대로 전파). 실패를 마지막 페이지로 오인해 잘린 목록을 돌려주면
            sync_post_active_status 가 멀쩡한 글을 비활성화하므로 유저 단위로
            실패시킨다(consumer 는 재시도).
    """
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
