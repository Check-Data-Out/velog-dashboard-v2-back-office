from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

# 클라이언트 타입을 위한 제네릭 타입 변수
T = TypeVar("T")


class LLMClient(ABC, Generic[T]):
    """
    모든 LLM 클라이언트를 위한 추상 기본 클래스로 Lazy Initialization 패턴을 따릅니다.
    모든 LLM 서비스 구현을 위한 템플릿을 제공합니다.
    """

    @classmethod
    @abstractmethod
    def get_client(cls, api_key: str) -> "LLMClient[T]":
        """
        LLM 클라이언트를 가져오거나 초기화합니다.

        Args:
            api_key: API 키 (필수)

        Returns:
            초기화된 클라이언트 인스턴스

        Raises:
            AuthenticationError: API 키가 유효하지 않은 경우
            ConnectionError: 서비스 연결에 실패한 경우
        """
        pass

    @classmethod
    @abstractmethod
    def _initialize_client(cls, api_key: str) -> T:
        """
        특정 LLM 클라이언트를 초기화하는 추상 메서드.
        각 구체적인 하위 클래스에서 구현되어야 합니다.

        Args:
            api_key: API 키 (필수)

        Returns:
            초기화된 클라이언트 인스턴스

        Raises:
            AuthenticationError: API 키가 유효하지 않은 경우
            ConnectionError: 서비스 연결에 실패한 경우
        """
        pass

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> str:
        """
        LLM을 사용하여 텍스트를 생성합니다.

        Args:
            prompt: 텍스트 생성을 위한 입력 프롬프트
            system_prompt: 시스템 프롬프트 (선택적)
            model: 사용할 모델 (선택적)
            **kwargs: LLM에 특화된 추가 인자

        Returns:
            LLM에서 생성된 텍스트

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 잘못된 입력 값
            ConnectionError: API 연결 실패
            GenerationError: 생성 과정에서 오류 발생
        """
        pass

    @abstractmethod
    def generate_embedding(
        self,
        text: str | list[str],
        model: str = "",
    ) -> list[float] | list[list[float]]:
        """
        LLM을 사용하여 텍스트 임베딩을 생성합니다.

        Args:
            text: 임베딩을 생성할 텍스트 또는 텍스트 목록
            model: 사용할 임베딩 모델 (선택적)

        Returns:
            벡터 임베딩, 여

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 잘못된 입력 값
            ConnectionError: API 연결 실패
            GenerationError: 생성 과정에서 오류 발생
        """
        pass

    @classmethod
    @abstractmethod
    def reset_client(cls) -> None:
        """
        클라이언트 인스턴스를 재설정합니다(테스트나 설정 변경 시 사용하기 위함)
        """
        pass
