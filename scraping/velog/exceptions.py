from typing import Any


class VelogError(Exception):
    """Velog API 관련 기본 예외 클래스"""

    pass


class VelogApiError(VelogError):
    """API 요청 실패 시 발생하는 예외"""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"API 오류 (상태 코드: {status}): {message}")


class VelogResponseError(VelogError):
    """응답 데이터 처리 중 발생하는 예외"""

    def __init__(self, message: str, response: dict[str, Any] | None = None):
        self.message = message
        self.response = response
        super().__init__(message)
