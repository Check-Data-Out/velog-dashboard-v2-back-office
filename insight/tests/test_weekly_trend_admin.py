from unittest.mock import patch

import pytest

from insight.models import WeeklyTrend
from utils.utils import get_local_now


@pytest.mark.django_db
class TestWeeklyTrendAdmin:
    """WeeklyTrendAdmin 테스트"""

    def test_week_range(self, weekly_trend_admin, weekly_trend: WeeklyTrend):
        """week_range 메소드 테스트"""
        result = weekly_trend_admin.week_range(weekly_trend)
        expected_format = f"{weekly_trend.week_start_date.strftime('%Y-%m-%d')} ~ {weekly_trend.week_end_date.strftime('%Y-%m-%d')}"
        assert expected_format in result

    def test_is_processed_colored_true(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """is_processed_colored 메소드 테스트 (처리 완료)"""
        weekly_trend.is_processed = True
        weekly_trend.save()

        result = weekly_trend_admin.is_processed_colored(weekly_trend)
        assert "green" in result
        assert "✓" in result

    def test_is_processed_colored_false(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """is_processed_colored 메소드 테스트 (미처리)"""
        weekly_trend.is_processed = False
        weekly_trend.save()

        result = weekly_trend_admin.is_processed_colored(weekly_trend)
        assert "red" in result
        assert "✗" in result

    def test_processed_at_formatted_with_date(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 있음)"""
        now = get_local_now()
        weekly_trend.processed_at = now
        weekly_trend.save()

        result = weekly_trend_admin.processed_at_formatted(weekly_trend)
        assert now.strftime("%Y-%m-%d %H:%M") == result

    def test_processed_at_formatted_no_date(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 없음)"""
        weekly_trend.processed_at = None
        weekly_trend.save()

        result = weekly_trend_admin.processed_at_formatted(weekly_trend)
        assert result == "-"

    def test_mark_as_processed(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend, request_factory
    ):
        """mark_as_processed 메소드 테스트"""
        weekly_trend.is_processed = False
        weekly_trend.processed_at = None
        weekly_trend.save()

        with patch("utils.utils.get_local_now") as mock_now:
            mock_now.return_value = get_local_now()
            weekly_trend_admin.mark_as_processed(
                request_factory,
                weekly_trend.__class__.objects.filter(pk=weekly_trend.pk),
            )

        weekly_trend.refresh_from_db()
        assert weekly_trend.is_processed is True
        assert weekly_trend.processed_at is not None
