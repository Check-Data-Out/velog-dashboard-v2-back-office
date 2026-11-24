from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from insight.models import (
    BATCH_STATE_KEY,
    BATCH_USER_ANALYSIS_COMPLETED,
    BATCH_USER_ANALYSIS_STARTED,
    UserWeeklyTrend,
    WeeklyTrend,
)


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


@pytest.mark.django_db
class TestWeeklyTrendThisWeek:
    """이번 주 행 판정과 _batch 표시"""

    def test_this_week_keeps_only_this_week_row(self):
        """이번 주 행은 고르고 지난주 행은 빼는지"""
        this_week = WeeklyTrend.objects.create(
            week_start_date=date(2026, 11, 16),
            week_end_date=date(2026, 11, 22),
        )
        WeeklyTrend.objects.create(
            week_start_date=date(2026, 11, 9),
            week_end_date=date(2026, 11, 15),
        )
        now = datetime(2026, 11, 24, 7, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        assert list(WeeklyTrend.objects.this_week(now)) == [this_week]

    def test_mark_batch_keeps_other_insight_keys(self, weekly_trend):
        """표시를 남겨도 분석 결과와 다른 표시는 그대로인지"""
        WeeklyTrend.objects.filter(pk=weekly_trend.pk).update(
            insight={
                **weekly_trend.insight,
                BATCH_STATE_KEY: {BATCH_USER_ANALYSIS_STARTED: "앞선 표시"},
            }
        )
        original_summary = weekly_trend.insight["trending_summary"]

        weekly_trend.mark_batch(BATCH_USER_ANALYSIS_COMPLETED)

        saved = WeeklyTrend.objects.get(pk=weekly_trend.pk).insight
        assert saved["trending_summary"] == original_summary
        assert saved[BATCH_STATE_KEY][BATCH_USER_ANALYSIS_STARTED] == (
            "앞선 표시"
        )
        assert saved[BATCH_STATE_KEY][BATCH_USER_ANALYSIS_COMPLETED]
        assert weekly_trend.insight == saved
