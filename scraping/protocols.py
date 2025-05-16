from typing import Any, Protocol


class HttpSession(Protocol):
    """HTTP 세션을 위한 프로토콜."""

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> Any:
        """
        HTTP POST 요청을 수행합니다.

        Args:
            url: 요청 URL
            json: 요청 본문 (JSON)
            headers: 요청 헤더
            cookies: 요청 쿠키

        Returns:
            HTTP 응답 객체
        """
        ...
