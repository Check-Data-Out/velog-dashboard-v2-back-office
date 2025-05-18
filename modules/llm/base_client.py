from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    """
    모든 LLM 클라이언트를 위한 추상 기본 클래스로 Lazy Initialization 패턴을 따릅니다.
    모든 LLM 서비스 구현을 위한 템플릿을 제공합니다.
    """

    _client: Any = None

    @classmethod
    def get_client(cls, api_key: str) -> Any:
        """
        LLM 클라이언트를 가져오거나 초기화합니다.

        매개변수:
            api_key: API 키 (필수)

        반환값:
            초기화된 클라이언트 인스턴스
        """
        if cls._client is None:
            if not api_key:
                raise ValueError("API 키가 필요합니다.")
            cls._client = cls._initialize_client(api_key)
        return cls._client

    @classmethod
    @abstractmethod
    def _initialize_client(cls, api_key: str) -> Any:
        """
        특정 LLM 클라이언트를 초기화하는 추상 메서드.
        각 구체적인 하위 클래스에서 구현되어야 합니다.

        매개변수:
            api_key: API 키 (필수)

        반환값:
            초기화된 클라이언트 인스턴스
        """
        pass

    @abstractmethod
    def generate_text(self, prompt: Any, **kwargs: Any) -> str:
        """
        LLM을 사용하여 텍스트를 생성합니다.

        매개변수:
            prompt: 텍스트 생성을 위한 입력 프롬프트
            **kwargs: LLM에 특화된 추가 인자

        반환값:
            LLM에서 생성된 텍스트
        """
        pass

    @classmethod
    def reset_client(cls) -> None:
        """
        클라이언트 인스턴스를 재설정합니다(테스트나 설정 변경 시 사용하기 위함)
        """
        cls._client = None
