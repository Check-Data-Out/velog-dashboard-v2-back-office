from dataclasses import dataclass

from modules.mail.schemas import EmailMessage


# templates/insight/index.html 데이터 스키마
@dataclass
class NewsletterContext:
    s_date: str
    e_date: str
    user: dict
    is_expired_token_user: bool
    weekly_trend_html: str
    user_weekly_trend_html: str | None = None


@dataclass
class Newsletter:
    user_id: int
    email_message: EmailMessage
