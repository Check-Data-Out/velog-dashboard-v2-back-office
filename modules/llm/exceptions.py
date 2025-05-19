class LLMError(Exception):
    """LLM 서비스 관련 기본 예외 클래스"""

    pass


class AuthenticationError(LLMError):
    """API 키 인증 실패 시 발생하는 예외"""

    pass


class ConnectionError(LLMError):
    """LLM 서비스 연결 실패 시 발생하는 예외"""

    pass


class GenerationError(LLMError):
    """텍스트 또는 임베딩 생성 중 발생하는 예외"""

    pass


class ClientNotInitializedError(LLMError):
    """클라이언트가 초기화되지 않았을 때 발생하는 예외"""

    pass
