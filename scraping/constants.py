from typing import Final

import aiohttp

V3_URL: Final[str] = "https://v3.velog.io/graphql"

# velog API 세션 단일 계층 타임아웃 (aiohttp 기본 total=300 은 배치 1유저를
# 5분까지 묶어 둔다). 초기값 — 배포 후 7일 `timeout` cause 빈도로 조정.
VELOG_HTTP_TIMEOUT = aiohttp.ClientTimeout(
    total=30, sock_connect=10, sock_read=20
)

VELOG_POSTS_QUERY: Final[str] = """
    query velogPosts($input: GetPostsInput!) {
        posts(input: $input) {
            id
            title
            url_slug
            likes
            views
            released_at
        }
    }
    """

CURRENT_USER_QUERY: Final[str] = """
    query currentUser {
        currentUser {
            id
            username
            email
            profile {
                thumbnail
            }
        }
    }
    """
