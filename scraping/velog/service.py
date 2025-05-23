from typing import Any

from scraping.velog.client import VelogClient
from scraping.velog.constants import (
    CURRENT_USER_QUERY,
    GET_POST_QUERY,
    POSTS_QUERY,
    POSTS_STATS_QUERY,
    TRENDING_POSTS_QUERY,
)
from scraping.velog.exceptions import VelogError
from scraping.velog.schemas import Post, PostStats, User


class VelogService:
    """
    Velog 비즈니스 로직 서비스
    VelogClient를 사용하여 도메인 로직 구현
    """

    def __init__(self, client: VelogClient):
        self.client = client

    async def validate_user(self) -> bool:
        """
        현재 사용자의 토큰 유효성을 검증합니다.

        Args:
            None

        Returns:
            bool: 토큰이 유효한 경우 True, 그렇지 않은 경우 False
        """
        try:
            user = await self.get_current_user()
            return user is not None
        except VelogError:
            return False

    async def get_current_user(self) -> User | None:
        """
        현재 인증된 사용자 정보를 조회합니다.

        Args:
            None

        Returns:
            User | None: 사용자 정보 객체, 인증 실패 시 None

        Raises:
            VelogError: API 요청 중 오류가 발생한 경우
        """
        response = await self.client.execute_query(
            self.client.v3_url, CURRENT_USER_QUERY
        )
        if not response or "currentUser" not in response:
            return None

        user_data = response["currentUser"]
        return User(
            id=user_data.get("id", ""),
            username=user_data.get("username", ""),
            email=user_data.get("email", ""),
        )

    async def get_posts(
        self, username: str, cursor: str = "", limit: int = 50, tag: str = ""
    ) -> list[Post]:
        """
        사용자의 게시물 목록을 조회합니다.

        Args:
            username: 사용자 아이디
            cursor: 페이지네이션을 위한 커서 (기본값: "")
            limit: 한번에 가져올 게시물 수 (기본값: 50, 최대: 50)
            tag: 태그로 필터링 (기본값: "")

        Returns:
            list[Post]: 게시물 객체 리스트

        Raises:
            VelogError: API 요청 중 오류가 발생한 경우
        """
        variables = {
            "input": {
                "cursor": cursor,
                "username": username,
                "limit": limit,
                "tag": tag,
            }
        }

        response = await self.client.execute_query(
            self.client.v3_url, POSTS_QUERY, variables
        )

        if not response or "posts" not in response:
            return []

        return [
            Post(
                id=post.get("id", ""),
                title=post.get("title", ""),
                short_description=post.get("short_description", ""),
                thumbnail=post.get("thumbnail"),
                url_slug=post.get("url_slug"),
                released_at=post.get("released_at"),
                updated_at=post.get("updated_at"),
                user=User(
                    id=post.get("user", {}).get("id", ""),
                    username=post.get("user", {}).get("username", ""),
                    email=post.get("user", {}).get("email", ""),
                ),
            )
            for post in response["posts"]
        ]

    async def get_all_posts(self, username: str) -> list[Post]:
        """
        사용자의 모든 게시물을 조회합니다.
        페이지네이션을 자동으로 처리하여 모든 게시물을 가져옵니다.

        Args:
            username: 사용자 아이디

        Returns:
            list[Post]: 모든 게시물 객체 리스트

        Raises:
            VelogError: API 요청 중 오류가 발생한 경우
        """
        cursor = ""
        all_posts = []

        while True:
            posts = await self.get_posts(username, cursor)
            if not posts:
                break

            all_posts.extend(posts)

            if posts and hasattr(posts[-1], "id"):
                cursor = posts[-1].id
            else:
                break

        return all_posts

    async def get_post_stats(self, post_id: str) -> PostStats | None:
        """
        특정 게시물의 통계 정보를 조회합니다.

        Args:
            post_id: 게시물 ID (UUID 형식)

        Returns:
            PostStats | None: 게시물 통계 객체, 조회 실패 시 None

        Raises:
            VelogError: API 요청 중 오류가 발생한 경우
        """
        variables = {"post_id": post_id}

        response = await self.client.execute_query(
            self.client.v2_cdn_url, POSTS_STATS_QUERY, variables, "GetStats"
        )

        if not response or "getStats" not in response:
            return None

        stats_data = response["getStats"]
        return PostStats(
            id=stats_data.get("id", ""),
            likes=stats_data.get("likes", 0),
            views=stats_data.get("views", 0),
        )

    async def get_post(self, post_uuid: str) -> Post | None:
        """
        특정 게시물의 상세 정보를 조회합니다.

        Args:
            post_uuid: 게시물 ID (UUID 형식)

        Returns:
            Post | None: 게시물 상세 정보 객체, 조회 실패 시 None

        Raises:
            VelogError: API 요청 중 오류가 발생한 경우
        """
        variables = {"id": post_uuid}

        response = await self.client.execute_query(
            self.client.v2_url, GET_POST_QUERY, variables
        )

        if not response or "post" not in response:
            return None

        post_data = response["post"]
        return Post(
            id=post_data.get("id", ""),
            title=post_data.get("title", ""),
            short_description=post_data.get("short_description", ""),
            body=post_data.get("body", ""),
            thumbnail=post_data.get("thumbnail"),
            is_markdown=post_data.get("is_markdown", False),
            is_temp=post_data.get("is_temp", False),
            url_slug=post_data.get("url_slug"),
            likes=post_data.get("likes", 0),
            views=post_data.get("views", 0),
            is_private=post_data.get("is_private", False),
            released_at=post_data.get("released_at"),
            created_at=post_data.get("created_at"),
            updated_at=post_data.get("updated_at"),
            user=User(
                id=post_data.get("user", {}).get("id", ""),
                username=post_data.get("user", {}).get("username", ""),
                email=post_data.get("user", {}).get("email", ""),
            ),
            tags=post_data.get("tags", []),
            comments_count=post_data.get("comments_count", 0),
            liked=post_data.get("liked", False),
        )

    async def get_trending_posts(
        self, limit: int = 20, offset: int = 0, timeframe: str = "week"
    ) -> list[Post]:
        """
        인기 게시물 목록을 조회합니다.

        Args:
            limit: 가져올 게시물 수 (기본값: 20)
            offset: 시작 위치 오프셋 (기본값: 0)
            timeframe: 기간 필터 (기본값: "week")
                      - 가능한 값: "day", "week", "month", "year"

        Returns:
            list[Post]: 인기 게시물 객체 리스트

        Raises:
            VelogError: API 요청 중 오류가 발생한 경우
        """
        variables = {
            "input": {"limit": limit, "offset": offset, "timeframe": timeframe}
        }

        response = await self.client.execute_query(
            self.client.v3_url, TRENDING_POSTS_QUERY, variables
        )

        if not response or "trendingPosts" not in response:
            return []

        return [
            Post(
                id=post.get("id", ""),
                title=post.get("title", ""),
                short_description=post.get("short_description", ""),
                thumbnail=post.get("thumbnail"),
                url_slug=post.get("url_slug"),
                released_at=post.get("released_at"),
                updated_at=post.get("updated_at"),
                likes=post.get("likes", 0),
                is_private=post.get("is_private", False),
                comments_count=post.get("comments_count", 0),
                user=User(
                    id=post.get("user", {}).get("id", ""),
                    username=post.get("user", {}).get("username", ""),
                    email=post.get("user", {}).get("email", ""),
                ),
            )
            for post in response["trendingPosts"]
        ]

    async def get_user_posts_with_stats(
        self, username: str
    ) -> list[dict[str, Any]]:
        """
        사용자의 모든 게시물과 각 게시물의 통계 정보를 함께 조회합니다.

        Args:
            username: 사용자 아이디

        Returns:
            list[dict[str, Any]]: 게시물 정보와 통계가 포함된 딕셔너리 리스트
                각 딕셔너리는 다음 구조를 가집니다:
                {
                    "id": str,
                    "title": str,
                    "short_description": str,
                    "url_slug": str,
                    "released_at": str,
                    "updated_at": str,
                    "stats": {
                        "likes": int,
                        "views": int
                    }
                }

        Raises:
            VelogError: API 요청 중 오류가 발생한 경우
        """
        posts = await self.get_all_posts(username)
        result = []

        for post in posts:
            try:
                stats = await self.get_post_stats(post.id)
                post_data = {
                    "id": post.id,
                    "title": post.title,
                    "short_description": post.short_description,
                    "url_slug": post.url_slug,
                    "released_at": post.released_at,
                    "updated_at": post.updated_at,
                    "stats": {
                        "likes": stats.likes if stats else 0,
                        "views": stats.views if stats else 0,
                    },
                }
                result.append(post_data)
            except VelogError:
                post_data = {
                    "id": post.id,
                    "title": post.title,
                    "short_description": post.short_description,
                    "url_slug": post.url_slug,
                    "released_at": post.released_at,
                    "updated_at": post.updated_at,
                    "stats": {"likes": 0, "views": 0},
                }
                result.append(post_data)

        return result
