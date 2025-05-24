import pytest

from insight.models import UserWeeklyTrend, WeeklyTrend


@pytest.mark.django_db
class TestModels:
    """모델 테스트"""

    def test_weekly_trend_str_method(self, weekly_trend: WeeklyTrend):
        """WeeklyTrend __str__ 메소드 테스트"""
        expected = f"주간 트렌드 ({weekly_trend.week_start_date} ~ {weekly_trend.week_end_date})"
        assert str(weekly_trend) == expected

    def test_user_weekly_trend_str_method(
        self, user_weekly_trend: UserWeeklyTrend
    ):
        """UserWeeklyTrend __str__ 메소드 테스트"""
        expected = f"{user_weekly_trend.user.email} 주간 인사이트 ({user_weekly_trend.week_start_date} ~ {user_weekly_trend.week_end_date})"
        assert str(user_weekly_trend) == expected
