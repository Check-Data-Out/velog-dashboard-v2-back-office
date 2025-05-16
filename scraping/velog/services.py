from typing import Any

from scraping.protocols import HttpSession
from scraping.velog.constants import (
    CURRENT_USER_QUERY,
    GET_POST_QUERY,
    POSTS_QUERY,
    POSTS_STATS_QUERY,
    TRENDING_POSTS_QUERY,
    V2_CDN_URL,
    V2_URL,
    V3_URL,
)
from scraping.velog.exceptions import (
    VelogApiError,
    VelogError,
    VelogResponseError,
)
from scraping.velog.schemas import Post, PostStats, User


class VelogService:
    def __init__(
        self,
        session: HttpSession,
        access_token: str,
        refresh_token: str,
    ):
        """
        VelogService 초기화

        Args:
            session: HTTP 세션 객체 (aiohttp.ClientSession, httpx.AsyncClient 등)
            access_token: Velog 액세스 토큰
            refresh_token: Velog 리프레시 토큰
        """

        self.session = session
        self.access_token = access_token
        self.refresh_token = refresh_token

        # API URL
        self.v3_url = V3_URL
        self.v2_url = V2_URL
        self.v2_cdn_url = V2_CDN_URL

    def _get_headers(self) -> dict[str, str]:
        """API 요청에 필요한 헤더를 생성합니다."""
        return {
            "authority": "v3.velog.io",
            "origin": "https://velog.io",
            "content-type": "application/json",
            "cookie": f"access_token={self.access_token}; refresh_token={self.refresh_token}",
        }

    async def _execute_query(
        self,
        url: str,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """
        GraphQL 쿼리를 실행합니다.

        Args:
            url: GraphQL 엔드포인트 URL
            query: GraphQL 쿼리 문자열
            variables: 쿼리 변수 딕셔너리
            operation_name: 작업 이름

        Returns:
            GraphQL 응답 데이터 딕셔너리

        Raises:
            VelogApiError: API 요청이 실패했을 때 발생합니다
            VelogResponseError: 응답 처리 중 오류가 발생했을 때 발생합니다
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        headers = self._get_headers()
        try:
            response = await self.session.post(
                url, json=payload, headers=headers
            )

            if response["status"] != 200:
                error_text = await response.text()
                raise VelogApiError(response["status"], error_text)

            result = await response.json()
            data = result.get("data")
            return data if isinstance(data, dict) else {}
        except (VelogApiError, VelogResponseError):
            # 이미 정의된 예외는 그대로 전파
            raise
        except Exception as e:
            # 기타 예외는 VelogError로 래핑하여 전파
            raise VelogError(f"API 요청 중 예외 발생: {str(e)}") from e

    async def validate_user(self) -> bool:
        """
        현재 사용자의 토큰 유효성을 검증합니다.

        Returns:
            토큰이 유효한 경우 True, 그렇지 않은 경우 False

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
        """
        try:
            user = await self.get_current_user()
            return user is not None
        except VelogError:
            return False

    async def get_current_user(self) -> User | None:
        """
        현재 인증된 사용자 정보를 가져옵니다.

        Returns:
            사용자 정보 객체 또는 인증 실패 시 None

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
        """
        response = await self._execute_query(self.v3_url, CURRENT_USER_QUERY)
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
        사용자의 게시물을 최근 기준 50개씩 가져옵니다.

        Args:
            username: 사용자 아이디
            cursor: 페이지네이션을 위한 커서
            limit: 한번에 가져올 게시물 수
            tag: 태그로 필터링

        Returns:
            게시물 목록

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
        """
        variables = {
            "input": {
                "cursor": cursor,
                "username": username,
                "limit": limit,
                "tag": tag,
            }
        }

        response = await self._execute_query(
            self.v3_url, POSTS_QUERY, variables
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
                user=post.get("user"),
            )
            for post in response["posts"]
        ]

    async def get_all_posts(self, username: str) -> list[Post]:
        """
        사용자의 모든 게시물을 가져옵니다.

        Args:
            username: 사용자 아이디

        Returns:
            모든 게시물 목록

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
        """
        cursor = ""
        all_posts = []

        while True:
            posts = await self.get_posts(username, cursor)
            if not posts:
                break

            all_posts.extend(posts)

            # 마지막 게시물의 ID를 다음 커서로 설정
            if posts and hasattr(posts[-1], "id"):
                cursor = posts[-1].id
            else:
                break

        return all_posts

    async def get_post_stats(self, post_id: str) -> PostStats | None:
        """
        게시물 통계를 가져옵니다.

        Args:
            post_id: 게시물 ID

        Returns:
            게시물 통계 객체 또는 오류 발생 시 None

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
        """
        variables = {"post_id": post_id}

        response = await self._execute_query(
            self.v2_cdn_url, POSTS_STATS_QUERY, variables, "GetStats"
        )

        if not response or "getStats" not in response:
            return None

        stats_data = response["getStats"]
        return PostStats(
            id=stats_data.get("id", ""),
            likes=stats_data.get("likes", 0),
            views=stats_data.get("views", 0),
        )

    async def get_user_posts_with_stats(
        self, username: str
    ) -> list[dict[str, Any]]:
        """
        사용자의 모든 게시물과 통계 정보를 가져옵니다.

        Args:
            username: 사용자 아이디

        Returns:
            게시물 및 통계 정보가 포함된 딕셔너리 목록

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
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
                # 개별 게시물 통계 조회 실패 시에도 전체 프로세스는 계속 진행
                post_data = {
                    "id": post.id,
                    "title": post.title,
                    "short_description": post.short_description,
                    "url_slug": post.url_slug,
                    "released_at": post.released_at,
                    "updated_at": post.updated_at,
                    "stats": {
                        "likes": 0,
                        "views": 0,
                    },
                }
                result.append(post_data)

        return result

    async def get_post(self, post_uuid: str) -> Post | None:
        """
        특정 게시물의 상세 정보를 가져옵니다.

        Args:
            post_uuid: 게시물 ID

        Returns:
            게시물 객체 또는 조회 실패 시 None

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
        """
        variables = {"id": post_uuid}

        response = await self._execute_query(
            self.v2_url, GET_POST_QUERY, variables
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
            user=post_data.get("user"),
            tags=post_data.get("tags", []),
            comments_count=post_data.get("comments_count", 0),
            liked=post_data.get("liked", False),
        )

    async def get_trending_posts(
        self, limit: int = 20, offset: int = 0, timeframe: str = "week"
    ) -> list[Post]:
        """
        인기 게시물 목록을 가져옵니다.

        Args:
            limit: 가져올 게시물 수
            offset: 오프셋
            timeframe: 기간 ('day', 'week', 'month', 'year' 중 하나)

        Returns:
            인기 게시물 목록

        Raises:
            VelogError: API 요청 중 오류가 발생했을 때 발생합니다
        """
        variables = {
            "input": {"limit": limit, "offset": offset, "timeframe": timeframe}
        }

        response = await self._execute_query(
            self.v3_url, TRENDING_POSTS_QUERY, variables
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
                user=post.get("user"),
            )
            for post in response["trendingPosts"]
        ]
