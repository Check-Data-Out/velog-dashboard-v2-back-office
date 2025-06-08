import json
import logging
from typing import Any, ClassVar

import boto3
from botocore.exceptions import ClientError

from modules.mail.base_client import MailClient
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
from modules.mail.schemas import (
    AWSSESCredentials,
    EmailMessage,
    TemplatedEmailMessage,
)

logger = logging.getLogger(__name__)


class SESClient(MailClient):
    """AWS SES를 사용하는 메일 클라이언트 구현체"""

    _instance: ClassVar["SESClient | None"] = None

    def __init__(self, client: Any):
        self._client = client

    @classmethod
    def get_client(cls, credentials: AWSSESCredentials) -> "SESClient":
        """
        SES 클라이언트를 가져오거나 초기화합니다.

        Args:
            credentials: AWS 인증 정보 (AWSSESCredentials)

        Returns:
            초기화된 SESClient 인스턴스

        Raises:
            AuthenticationError: AWS 인증 정보가 유효하지 않은 경우
            LimitExceededException: AWS API 호출 제한을 초과한 경우
            ValidationError: 입력이 유효하지 않은 경우
            ConnectionError: AWS 서비스 연결에 실패한 경우
        """
        if cls._instance is None:
            try:
                client = cls._initialize_client(credentials)
                cls._instance = cls(client)
            except Exception as e:
                logger.error(f"AWS SES 클라이언트 초기화 실패: {str(e)}")
                raise  # 예외 전파

        return cls._instance

    @classmethod
    def _initialize_client(cls, credentials: AWSSESCredentials) -> Any:
        """
        AWS SES 클라이언트를 초기화합니다.

        Args:
            credentials: AWS 인증 정보 (AWSSESCredentials)

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
                aws_access_key_id=credentials.aws_access_key_id,
                aws_secret_access_key=credentials.aws_secret_access_key,
                region_name=credentials.aws_region_name,
            )
            # API 키 검증을 위한 간단한 호출
            client.get_account_sending_enabled()
            return client
        except ClientError as e:
            # 공통 에러 처리
            cls._handle_aws_common_errors(e)
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
            message: 발송할 이메일 메시지 객체

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

        try:
            email_args = {
                "Source": message.from_email,
                "Destination": {
                    "ToAddresses": message.to,
                },
                "Message": {
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": message.text_body, "Charset": "UTF-8"}
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
            # 공통 에러 처리
            self._handle_aws_common_errors(e)
            # 특정 에러 처리
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

    def send_templated_email(self, message: TemplatedEmailMessage) -> str:
        """
        템플릿을 사용하여 이메일을 발송합니다.

        Args:
            message: 발송할 템플릿 이메일 메시지 객체

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
            # 템플릿 데이터 JSON 직렬화
            try:
                template_data_json = json.dumps(message.template_data or {})
            except (TypeError, ValueError) as json_error:
                logger.error(f"템플릿 데이터 JSON 직렬화 실패: {str(json_error)}")
                raise ValueError(f"템플릿 데이터 JSON 직렬화 실패: {str(json_error)}") from json_error

            email_args = {
                "Source": message.from_email,
                "Destination": {
                    "ToAddresses": message.to,
                },
                "Template": message.template_name,
                "TemplateData": template_data_json,
            }

            # CC, BCC 추가
            if message.cc:
                email_args["Destination"]["CcAddresses"] = message.cc
            if message.bcc:
                email_args["Destination"]["BccAddresses"] = message.bcc

            response = self._client.send_templated_email(**email_args)
            return response["MessageId"]

        except ClientError as e:
            # 공통 에러 처리
            self._handle_aws_common_errors(e)
            # 특정 에러 처리
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

    @classmethod
    def reset_client(cls) -> None:
        """
        클라이언트 인스턴스를 재설정합니다.
        """
        cls._instance = None

    @staticmethod
    def _handle_aws_common_errors(e: ClientError) -> None:
        """
        AWS Common ClientError를 처리하고 적절한 예외를 발생시킵니다.

        Args:
            e: ClientError 객체

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
