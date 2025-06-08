from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from modules.mail.schemas import EmailMessage

# 클라이언트 타입을 위한 제네릭 타입 변수
T = TypeVar("T")

class MailClient(ABC, Generic[T]):
    """
    모든 메일 클라이언트를 위한 추상 기본 클래스로 Lazy Initialization 패턴을 따릅니다.
    모든 메일 서비스 구현을 위한 템플릿을 제공합니다.
    """

    @classmethod
    @abstractmethod
    def get_client(cls, credentials: dict[str, Any]) -> "MailClient[T]":
        """
        메일 클라이언트를 가져오거나 초기화합니다.

        Args:
            credentials: 서비스 인증 정보 (필수)

        Returns:
            초기화된 클라이언트 인스턴스

        Raises:
            AuthenticationError: 인증 정보가 유효하지 않은 경우
            ConnectionError: 서비스 연결에 실패한 경우
        """
        pass

    @classmethod
    @abstractmethod
    def _initialize_client(cls, credentials: dict[str, Any]) -> T:
        """
        특정 메일 클라이언트를 초기화하는 추상 메서드.
        각 구체적인 하위 클래스에서 구현되어야 합니다.

        Args:
            credentials: 서비스 인증 정보 (필수)

        Returns:
            초기화된 클라이언트 인스턴스

        Raises:
            AuthenticationError: 인증 정보가 유효하지 않은 경우
            ConnectionError: 서비스 연결에 실패한 경우
        """
        pass

    @abstractmethod
    def send_email(self, message: EmailMessage) -> str:
        """
        이메일을 발송합니다.

        Args:
            message: 발송할 이메일 메시지 객체

        Returns:
            발송한 메시지 ID

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            AuthenticationError: 인증 정보가 유효하지 않은 경우
            ValidationError: 입력이 유효하지 않은 경우
            LimitExceededException: 발송 한도를 초과한 경우
            SendError: 이메일 발송 과정에서 오류 발생
            ConnectionError: API 연결 실패
        """
        pass

    @classmethod
    @abstractmethod
    def reset_client(cls) -> None:
        """
        클라이언트 인스턴스를 재설정합니다(테스트나 설정 변경 시 사용하기 위함)
        """
        pass
