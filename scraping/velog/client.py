from typing import TYPE_CHECKING, Any

from scraping.protocols import HttpSession
from scraping.velog.schemas import Post, PostStats, User


class VelogClient:
    """
    Velog API 클라이언트 - Facade Pattern with Lazy Initialization Singleton
    Client는 싱글톤으로 관리되며, Service 로직의 진입점 역할
    """

    if TYPE_CHECKING:
        # circular import 때문에 dynamic import
        from scraping.velog.service import VelogService

        _instance: "VelogClient" | None = None
        _service: "VelogService" | None = None
    else:
        _instance = None
        _service = None

    _session: HttpSession | None = None
    _access_token: str | None = None
    _refresh_token: str | None = None

    def __init__(
        self, session: HttpSession, access_token: str, refresh_token: str
    ):
        """
        Private constructor. Use get_client() instead.

        Args:
            session: HTTP 세션 객체
            access_token: Velog 액세스 토큰
            refresh_token: Velog 리프레시 토큰
        """
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token

        # Service 도 lazy initialization
        self._service = None

    @classmethod
    def get_client(
        cls,
        session: HttpSession,
        access_token: str = "",
        refresh_token: str = "",
    ) -> "VelogClient":
        """
        싱글톤 인스턴스를 반환합니다.

        Args:
            session: HTTP 세션 객체 (aiohttp.ClientSession 등)
            access_token: Velog 액세스 토큰. 첫 호출 시 필수, 이후 선택적
            refresh_token: Velog 리프레시 토큰. 첫 호출 시 필수, 이후 선택적

        Returns:
            VelogClient: 초기화된 클라이언트 인스턴스

        Raises:
            ValueError: 첫 호출 시 토큰이 없거나 세션이 없는 경우
        """
        if cls._instance is None and (not access_token or not refresh_token):
            raise ValueError(
                "첫 호출 시 access_token과 refresh_token은 필수입니다."
            )

        if not session:
            raise ValueError("session은 필수입니다.")

        if cls._instance is None:
            cls._instance = cls(session, access_token, refresh_token)
            cls._session = session
            cls._access_token = access_token
            cls._refresh_token = refresh_token
        else:
            if access_token and refresh_token:
                cls._instance.update_tokens(access_token, refresh_token)
            cls._session = session
            if cls._service:
                cls._service.session = session

        return cls._instance

    def update_tokens(self, access_token: str, refresh_token: str) -> None:
        """
        현재 인스턴스의 토큰을 업데이트합니다.

        Args:
            access_token: 새로운 Velog 액세스 토큰
            refresh_token: 새로운 Velog 리프레시 토큰

        Returns:
            None
        """
        VelogClient._access_token = access_token
        VelogClient._refresh_token = refresh_token
        if self._service:
            self._service.access_token = access_token
            self._service.refresh_token = refresh_token

    @property
    def service(self) -> "VelogService":
        """
        VelogService 인스턴스를 반환합니다. (Lazy initialization)

        Returns:
            VelogService: 서비스 인스턴스
        """
        if self._service is None:
            if (
                not self._session
                or not self._access_token
                or not self._refresh_token
            ):
                raise ValueError(
                    "서비스를 사용하기 전에 세션과 토큰을 설정해야 합니다."
                )

            from scraping.velog.service import VelogService

            self._service = VelogService(
                self._session, self._access_token, self._refresh_token
            )
        return self._service

    async def validate_user(self) -> bool:
        """
        현재 사용자의 토큰 유효성을 검증합니다.

        Args:
            None

        Returns:
            bool: 토큰이 유효한 경우 True, 그렇지 않은 경우 False
        """
        return await self.service.validate_user()

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
        return await self.service.get_current_user()

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
        return await self.service.get_posts(username, cursor, limit, tag)

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
        return await self.service.get_all_posts(username)

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
        return await self.service.get_post_stats(post_id)

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
        return await self.service.get_post(post_uuid)

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
        return await self.service.get_trending_posts(limit, offset, timeframe)

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
        return await self.service.get_user_posts_with_stats(username)

    @classmethod
    def reset_client(cls) -> None:
        """
        클라이언트 인스턴스를 재설정합니다.
        주로 테스트나 설정 변경 시 사용됩니다.

        Args:
            None

        Returns:
            None
        """
        cls._instance = None
        cls._session = None
        cls._access_token = None
        cls._refresh_token = None
        cls._service = None
