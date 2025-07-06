from dataclasses import dataclass

from insight.models import WeeklyTrendInsight
from modules.mail.schemas import EmailMessage


# templates/insight/index.html 데이터 스키마
@dataclass
class NewsletterContext:
    s_date: str
    e_date: str
    is_expired_token_user: bool
    weekly_trend_html: str | None = None
    user_weekly_trend_html: str | None = None


# templates/insight/weekly_trend.html 데이터 스키마
@dataclass
class WeeklyTrendContext:
    insight: WeeklyTrendInsight


# templates/insight/user_weekly_trend.html 데이터 스키마
@dataclass
class UserWeeklyTrendContext:
    user: dict[str, str]  # username
    user_weekly_stats: dict[str, int]  # posts, views, likes
    insight: WeeklyTrendInsight


@dataclass
class Newsletter:
    user_id: int
    email_message: EmailMessage
