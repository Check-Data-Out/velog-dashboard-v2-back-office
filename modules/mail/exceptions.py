class MailError(Exception):
    """메일 관련 모든 예외의 기본 클래스"""

    pass


class AuthenticationError(MailError):
    """인증 관련 오류"""

    pass


class ConnectionError(MailError):
    """서비스 연결 오류"""

    pass


class ClientNotInitializedError(MailError):
    """클라이언트가 초기화되지 않은 경우"""

    pass


class SendError(MailError):
    """이메일 발송 중 발생한 오류"""

    pass

class LimitExceededException(MailError):
    """메일 서비스 할당량 초과 오류"""

    pass


class ValidationError(MailError):
    """API 입력이 유효하지 않은 오류"""

    pass

class UnexpectedClientError(MailError):
    """예상하지 못한 ClientError"""

    pass