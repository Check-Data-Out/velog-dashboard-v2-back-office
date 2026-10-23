from collections.abc import Iterator
from unittest.mock import patch

import boto3
import pytest
from botocore.client import BaseClient
from botocore.stub import Stubber

from modules.mail.schemas import AWSSESCredentials, EmailMessage
from modules.mail.ses.client import SESClient


@pytest.fixture
def sesv2_client() -> BaseClient:
    """네트워크 호출 없이 Stubber 로 응답을 지정할 boto3 sesv2 클라이언트"""
    return boto3.client(
        "sesv2",
        region_name="ap-northeast-2",
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
    )


@pytest.fixture
def stubber(sesv2_client: BaseClient) -> Iterator[Stubber]:
    with Stubber(sesv2_client) as stub:
        yield stub
        stub.assert_no_pending_responses()


def test_send_email_maps_message_to_sesv2_simple_content(
    sesv2_client: BaseClient, stubber: Stubber
) -> None:
    """발신자와 본문을 SES v2 FromEmailAddress, Content.Simple 로 보낸다."""
    stubber.add_response(
        "send_email",
        {"MessageId": "message-id"},
        {
            "FromEmailAddress": "from@example.com",
            "Destination": {"ToAddresses": ["to@example.com"]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": "제목", "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": "본문", "Charset": "UTF-8"},
                        "Html": {"Data": "<p>본문</p>", "Charset": "UTF-8"},
                    },
                }
            },
        },
    )

    message_id = SESClient(sesv2_client).send_email(
        EmailMessage(
            to=["to@example.com"],
            from_email="from@example.com",
            subject="제목",
            text_body="본문",
            html_body="<p>본문</p>",
        )
    )

    assert message_id == "message-id"


def test_initialize_client_creates_sesv2_without_account_check(
    sesv2_client: BaseClient, stubber: Stubber
) -> None:
    """sesv2 클라이언트를 만들고 초기화 시점에는 AWS API 를 호출하지 않는다."""
    with patch(
        "modules.mail.ses.client.boto3.client", return_value=sesv2_client
    ) as mock_boto3_client:
        client = SESClient._initialize_client(
            AWSSESCredentials(
                aws_access_key_id="test-access-key",
                aws_secret_access_key="test-secret-key",
                aws_region_name="ap-northeast-2",
            )
        )

    assert client is sesv2_client
    assert mock_boto3_client.call_args.kwargs["service_name"] == "sesv2"


def test_send_email_puts_headers_into_simple_content(
    sesv2_client: BaseClient, stubber: Stubber
) -> None:
    """메시지 헤더를 SES v2 Content.Simple.Headers 로 보낸다."""
    unsubscribe_url = "https://example.com/unsubscribe?uid=1&sig=abc"
    stubber.add_response(
        "send_email",
        {"MessageId": "message-id"},
        {
            "FromEmailAddress": "from@example.com",
            "Destination": {"ToAddresses": ["to@example.com"]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": "제목", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": "본문", "Charset": "UTF-8"}},
                    "Headers": [
                        {
                            "Name": "List-Unsubscribe",
                            "Value": f"<{unsubscribe_url}>",
                        },
                        {
                            "Name": "List-Unsubscribe-Post",
                            "Value": "List-Unsubscribe=One-Click",
                        },
                    ],
                }
            },
        },
    )

    SESClient(sesv2_client).send_email(
        EmailMessage(
            to=["to@example.com"],
            from_email="from@example.com",
            subject="제목",
            text_body="본문",
            headers=[
                ("List-Unsubscribe", f"<{unsubscribe_url}>"),
                ("List-Unsubscribe-Post", "List-Unsubscribe=One-Click"),
            ],
        )
    )
