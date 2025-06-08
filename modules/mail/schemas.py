from dataclasses import dataclass
from typing import Any


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str


@dataclass
class EmailMessage:
    to: list[str]
    from_email: str
    subject: str
    text_body: str
    html_body: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    attachments: list[EmailAttachment] | None = None

@dataclass
class AWSSESCredentials:
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region_name: str