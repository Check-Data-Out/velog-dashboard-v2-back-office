from typing import Any, Awaitable, Protocol


class HttpSession(Protocol):
    """HTTP 비동기 세션을 위한 프로토콜."""

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> Awaitable[Any]:
        """
        HTTP POST 요청을 수행합니다.

        Args:
            url: 요청 URL
            json: 요청 본문 (JSON)
            headers: 요청 헤더
            cookies: 요청 쿠키

        Returns:
            비동기 컨텍스트 관리자 (async with에서 사용 가능)
        """
        ...
