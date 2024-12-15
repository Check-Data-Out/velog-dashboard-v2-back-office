import logging

from aiohttp.client import ClientSession

from scraping.constants import CURRENT_USER_QUERY, V3_URL, VELOG_POSTS_QUERY

logger = logging.getLogger(__name__)


# async def fetch_all_posts_stats(
#     user: UserInfo, all_post_stats_result: dict
# ) -> list[PostStats]:
#     return [
#         PostStats(
#             userId=user.userId,
#             uuid=post_id,
#             url=post_data["url"],
#             title=post_data["title"],
#             stats=[
#                 Stats(
#                     date=daily_cnt["day"],
#                     viewCount=daily_cnt["count"],
#                     likeCount=post_data["likes"],
#                 )
#                 for daily_cnt in post_data.get("stats", [])
#             ],
#             totalViewCount=post_data.get("total", 0),
#         )
#         for post_id, post_data in all_post_stats_result.items()
#     ]


async def fetch_velog_user_chk(
    session: ClientSession,
    access_token: str,
    refresh_token: str,
) -> tuple[dict[str, str], dict[str, str]]:
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
            cookie.key: cookie.value for cookie in response.cookies.values()
        }
        return cookies, data


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
        posts: list[dict[str, str]] = data["data"]["posts"]
        return posts
