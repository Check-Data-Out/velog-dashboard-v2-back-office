import json
import logging
from typing import Any, ClassVar

import boto3
from botocore.exceptions import ClientError

from modules.mail.base_client import EmailMessage, MailClient
from modules.mail.constants import (
    AWS_AUTH_ERROR_CODES,
    AWS_LIMIT_ERROR_CODES,
    AWS_SERVICE_ERROR_CODES,
    AWS_VALUE_ERROR_CODES,
)
from modules.mail.exceptions import (
    AuthenticationError,
    ClientNotInitializedError,
    ConnectionError,
    LimitExceededException,
    SendError,
    TemplateError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class SESClient(MailClient):
    """AWS SES를 사용하는 메일 클라이언트 구현체"""

    _instance: ClassVar["SESClient | None"] = None

    def __init__(self, client: Any):
        self._client = client

    @classmethod
    def get_client(cls, credentials: dict[str, Any]) -> "SESClient":
        """
        SES 클라이언트를 가져오거나 초기화합니다.

        Args:
            credentials: AWS 인증 정보 (aws_access_key_id, aws_secret_access_key, aws_region_name)

        Returns:
            초기화된 SESClient 인스턴스

        Raises:
            ValueError: AWS 인증 정보가 입력되지 않은 경우
            AuthenticationError: AWS 인증 정보가 유효하지 않은 경우
            LimitExceededException: AWS API 호출 제한을 초과한 경우
            ValidationError: 입력이 유효하지 않은 경우
            ConnectionError: AWS 서비스 연결에 실패한 경우
        """
        if (
            not credentials.get("aws_access_key_id")
            or not credentials.get("aws_secret_access_key")
            or not credentials.get("aws_region_name")
        ):
            raise ValueError("AWS 인증 정보가 필요합니다.")

        if cls._instance is None:
            try:
                client = cls._initialize_client(credentials)
                cls._instance = cls(client)
            except Exception as e:
                logger.error(f"AWS SES 클라이언트 초기화 실패: {str(e)}")
                raise  # 예외 전파

        return cls._instance

    @classmethod
    def _initialize_client(cls, credentials: dict[str, Any]) -> Any:
        """
        AWS SES 클라이언트를 초기화합니다.

        Args:
            credentials: AWS 인증 정보 (aws_access_key_id, aws_secret_access_key, aws_region_name)

        Returns:
            초기화된 boto3 SES 클라이언트

        Raises:
            AuthenticationError: AWS 인증 정보가 유효하지 않은 경우
            LimitExceededException: AWS API 호출 제한을 초과한 경우
            ValidationError: 입력이 유효하지 않은 경우
            ConnectionError: AWS 서비스 연결에 실패한 경우
        """
        try:
            client = boto3.client(
                service_name="ses",
                aws_access_key_id=credentials["aws_access_key_id"],
                aws_secret_access_key=credentials["aws_secret_access_key"],
                region_name=credentials["aws_region_name"],
            )
            # API 키 검증을 위한 간단한 호출
            client.get_account_sending_enabled()
            return client
        except ClientError as e:
            if not cls._handle_aws_common_error(e):
                logger.error(f"AWS SES 클라이언트 초기화 실패: {str(e)}")
                raise ConnectionError(
                    f"AWS SES 클라이언트 초기화 실패: {str(e)}"
                ) from e
        except Exception as e:
            logger.error(f"AWS SES 클라이언트 초기화 실패: {str(e)}")
            raise ConnectionError(
                f"AWS SES 클라이언트 초기화 실패: {str(e)}"
            ) from e

    def send_email(self, message: EmailMessage) -> str:
        """
        기본 이메일을 발송합니다.

        Args:
            message: 발송할 메일 메시지 객체

        Returns:
            발송한 메일 ID

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 메일 정보가 입력되지 않은 경우
            SendError: 이메일 발송 과정 오류
            AuthenticationError: AWS 인증 정보가 유효하지 않은 경우
            LimitExceededException: AWS API 호출 제한을 초과한 경우
            ValidationError: 입력이 유효하지 않은 경우
            ConnectionError: AWS 서비스 연결에 실패한 경우
        """
        if self._client is None:
            raise ClientNotInitializedError(
                "SES 클라이언트가 초기화되지 않았습니다. get_client()를 먼저 호출하세요."
            )

        if (
            not message.from_email
            or not message.to
            or not message.subject
            or not message.body
        ):
            raise ValueError("발송할 메일 정보가 필요합니다.")

        try:
            email_args = {
                "Source": message.from_email,
                "Destination": {
                    "ToAddresses": message.to,
                },
                "Message": {
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": message.body, "Charset": "UTF-8"}
                    },
                },
            }

            # CC, BCC 추가
            if message.cc:
                email_args["Destination"]["CcAddresses"] = message.cc
            if message.bcc:
                email_args["Destination"]["BccAddresses"] = message.bcc

            # HTML 본문 추가
            if message.html_body:
                email_args["Message"]["Body"]["Html"] = {
                    "Data": message.html_body,
                    "Charset": "UTF-8",
                }

            response = self._client.send_email(**email_args)
            return response["MessageId"]

        except ClientError as e:
            if not self._handle_aws_common_error(e):
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "MessageRejected":
                    logger.error(f"이메일이 거부되었습니다. {str(e)}")
                    raise SendError(
                        f"이메일이 거부되었습니다. {str(e)}"
                    ) from e
                if error_code == "AccountSendingPausedException":
                    logger.error(
                        f"계정의 이메일 발송이 일시 중지되었습니다. {str(e)}"
                    )
                    raise SendError(
                        f"계정의 이메일 발송이 일시 중지되었습니다. {str(e)}"
                    ) from e
                logger.error(f"이메일 발송 실패: {str(e)}")
                raise SendError(f"이메일 발송 실패: {str(e)}") from e
        except Exception as e:
            logger.error(f"이메일 발송 실패: {str(e)}")
            raise SendError(f"이메일 발송 실패: {str(e)}") from e

    def send_templated_email(self, message: EmailMessage) -> str:
        """
        템플릿을 사용하여 이메일을 발송합니다.

        Args:
            message: 발송할 이메일 메시지 (template_name과 template_data가 필수)

        Returns:
            메시지 ID

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 템플릿 이름이 입력되지 않은 경우
            AuthenticationError: AWS 인증 정보가 유효하지 않은 경우
            LimitExceededException: AWS API 호출 제한을 초과한 경우
            ValidationError: 입력이 유효하지 않은 경우
            ConnectionError: AWS 서비스 연결에 실패한 경우
            TemplateError: 템플릿이 존재하지 않는 경우
            SendError: 이메일 발송 과정 오류
        """
        if self._client is None:
            raise ClientNotInitializedError(
                "SES 클라이언트가 초기화되지 않았습니다. get_client()를 먼저 호출하세요."
            )

        if not message.template_name:
            raise ValueError("발송할 템플릿 정보가 필요합니다.")

        try:
            email_args = {
                "Source": message.from_email,
                "Destination": {
                    "ToAddresses": message.to,
                },
                "Template": message.template_name,
                "TemplateData": json.dumps(message.template_data or {}),
            }

            # CC, BCC 추가
            if message.cc:
                email_args["Destination"]["CcAddresses"] = message.cc
            if message.bcc:
                email_args["Destination"]["BccAddresses"] = message.bcc

            response = self._client.send_templated_email(**email_args)
            return response["MessageId"]

        except ClientError as e:
            if not self._handle_aws_common_error(e):
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "TemplateDoesNotExistException":
                    logger.error(
                        f"템플릿 '{message.template_name}'이(가) 존재하지 않습니다."
                    )
                    raise TemplateError(
                        f"템플릿 '{message.template_name}'이(가) 존재하지 않습니다."
                    ) from e
                logger.error(f"템플릿 이메일 발송 실패: {str(e)}")
                raise SendError(f"템플릿 이메일 발송 실패: {str(e)}") from e
        except Exception as e:
            logger.error(f"템플릿 이메일 발송 실패: {str(e)}")
            raise SendError(f"템플릿 이메일 발송 실패: {str(e)}") from e

    def create_template(
        self, template_name: str, subject: str, html: str = "", text: str = ""
    ) -> None:
        """
        이메일 템플릿을 생성합니다.

        Args:
            template_name: 템플릿 이름
            subject: 이메일 제목
            html: HTML 형식의 이메일 본문
            text: 텍스트 형식의 이메일 본문

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 템플릿 정보가 입력되지 않은 경우
            AuthenticationError: 인증 정보가 유효하지 않은 경우
            ValidationError: 입력이 유효하지 않은 경우
            LimitExceededException: API 호출 한도를 초과한 경우
            ConnectionError: AWS 서비스 연결에 실패한 경우
            TemplateError: 템플릿 생성 실패한 경우
        """
        if self._client is None:
            raise ClientNotInitializedError(
                "SES 클라이언트가 초기화되지 않았습니다. get_client()를 먼저 호출하세요."
            )

        if not template_name or not subject:
            raise ValueError("템플릿 이름과 제목이 필요합니다.")
        if not html and not text:
            raise ValueError("HTML 또는 텍스트 본문 중 하나는 필수입니다.")

        try:
            template_data = {
                "TemplateName": template_name.strip(),
                "SubjectPart": subject.strip(),
            }

            if html:
                template_data["HtmlPart"] = html
            if text:
                template_data["TextPart"] = text

            self._client.create_template(Template=template_data)
            logger.info(f"템플릿 '{template_name}' 생성 완료")
        except ClientError as e:
            if not self._handle_aws_common_error(e):
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "AlreadyExistsException":
                    logger.error(
                        f"템플릿 '{template_name}'이(가) 이미 존재합니다."
                    )
                    raise TemplateError(
                        f"템플릿 '{template_name}'이(가) 이미 존재합니다."
                    ) from e
                logger.error(f"템플릿 생성 실패: {str(e)}")
                raise TemplateError(f"템플릿 생성 실패: {str(e)}") from e
        except Exception as e:
            logger.error(f"템플릿 생성 실패: {str(e)}")
            raise TemplateError(f"템플릿 생성 실패: {str(e)}") from e

    def delete_template(self, template_name: str) -> None:
        """
        이메일 템플릿을 삭제합니다.

        Args:
            template_name: 삭제할 템플릿 이름

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 템플릿 정보가 입력되지 않은 경우
            AuthenticationError: 인증 정보가 유효하지 않은 경우
            ValidationError: 입력이 유효하지 않은 경우
            LimitExceededException: API 호출 한도를 초과한 경우
            ConnectionError: AWS 서비스 연결에 실패한 경우
            TemplateError: 템플릿 삭제 실패한 경우
        """
        if self._client is None:
            raise ClientNotInitializedError(
                "SES 클라이언트가 초기화되지 않았습니다. get_client()를 먼저 호출하세요."
            )
        if not template_name:
            raise ValueError("템플릿 이름이 필요합니다.")

        try:
            self._client.delete_template(TemplateName=template_name.strip())
            logger.info(f"템플릿 '{template_name}' 삭제 완료")

        except ClientError as e:
            if not self._handle_aws_common_error(e):
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "NotFoundException":
                    logger.error(
                        f"템플릿 '{template_name}'을(를) 찾을 수 없습니다."
                    )
                    raise TemplateError(
                        f"템플릿 '{template_name}'을(를) 찾을 수 없습니다."
                    ) from e
                logger.error(f"템플릿 삭제 실패: {str(e)}")
                raise TemplateError(f"템플릿 삭제 실패: {str(e)}") from e
        except Exception as e:
            logger.error(f"템플릿 삭제 실패: {str(e)}")
            raise TemplateError(f"템플릿 삭제 실패: {str(e)}") from e

    @classmethod
    def reset_client(cls) -> None:
        """
        클라이언트 인스턴스를 재설정합니다.
        """
        cls._instance = None

    @staticmethod
    def _handle_aws_common_error(e: ClientError) -> bool:
        """
        AWS Common ClientError를 처리하고 적절한 예외를 발생시킵니다.

        Args:
            e: ClientError 객체

        Returns:
            bool: Common ClientError 처리 여부

        Raises:
            AuthenticationError: AWS 인증 실패
            LimitExceededException: AWS API 호출 제한 초과
            ValidationError: AWS 값 오류
            ConnectionError: AWS 서비스 오류
        """
        error_code = e.response.get("Error", {}).get("Code", "")

        if error_code in AWS_AUTH_ERROR_CODES:
            logger.error(f"AWS 인증 실패: {str(e)}")
            raise AuthenticationError(f"AWS 인증 실패: {str(e)}") from e
        if error_code in AWS_LIMIT_ERROR_CODES:
            logger.error(f"AWS API 호출 제한 초과: {str(e)}")
            raise LimitExceededException(
                f"AWS API 호출 제한 초과: {str(e)}"
            ) from e
        if error_code in AWS_VALUE_ERROR_CODES:
            logger.error(f"AWS 값 오류: {str(e)}")
            raise ValidationError(f"AWS 값 오류: {str(e)}") from e
        if error_code in AWS_SERVICE_ERROR_CODES:
            logger.error(f"AWS 서비스 오류: {str(e)}")
            raise ConnectionError(f"AWS 서비스 오류: {str(e)}") from e
        
        return False # Common ClientError가 아닌 경우
