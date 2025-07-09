from dataclasses import dataclass

from insight.models import WeeklyTrendInsight
from modules.mail.schemas import EmailMessage


# templates/insight/index.html 데이터 스키마
@dataclass
class NewsletterContext:
    s_date: str
    e_date: str
    is_expired_token_user: bool
    weekly_trend_html: str
    user_weekly_trend_html: str | None = None


# templates/insight/weekly_trend.html 데이터 스키마
@dataclass
class WeeklyTrendContext:
    insight: WeeklyTrendInsight


# templates/insight/user_weekly_trend.html 데이터 스키마
@dataclass
class UserWeeklyTrendContext:
    user: dict[str, str]  # username
    user_weekly_stats: dict[str, int] | None  # posts, views, likes
    reminder: (
        dict[str, str] | None
    )  # title, days_ago (주간 글 미작성 유저 리마인드)
    insight: WeeklyTrendInsight | None


@dataclass
class Newsletter:
    user_id: int
    email_message: EmailMessage
