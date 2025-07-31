from unittest.mock import patch

import pytest

from insight.models import UserWeeklyTrend
from utils.utils import get_local_now


@pytest.mark.django_db
class TestUserWeeklyTrendAdmin:
    """UserWeeklyTrendAdmin 테스트"""

    def test_get_queryset(
        self,
        user_weekly_trend_admin,
        user_weekly_trend: UserWeeklyTrend,
        request_factory,
    ):
        """get_queryset 메소드 테스트"""
        qs = user_weekly_trend_admin.get_queryset(request_factory)
        assert user_weekly_trend in qs
        # select_related 검증은 어려우므로 메소드가 에러 없이 실행되는지만 확인

    def test_user_info(self, user_weekly_trend_admin, user_weekly_trend):
        """user_info 메소드 테스트"""
        with patch("django.urls.reverse") as mock_reverse:
            mock_reverse.return_value = (
                f"/admin/users/user/{user_weekly_trend.user.id}/change/"
            )
            result = user_weekly_trend_admin.user_info(user_weekly_trend)

        assert user_weekly_trend.user.username in result

    def test_week_range(
        self, user_weekly_trend_admin, user_weekly_trend: UserWeeklyTrend
    ):
        """week_range 메소드 테스트"""
        result = user_weekly_trend_admin.week_range(user_weekly_trend)
        expected_format = f"{user_weekly_trend.week_start_date.strftime('%Y-%m-%d')} ~ {user_weekly_trend.week_end_date.strftime('%Y-%m-%d')}"
        assert expected_format in result

    def test_is_processed_colored_true(
        self, user_weekly_trend_admin, user_weekly_trend: UserWeeklyTrend
    ):
        """is_processed_colored 메소드 테스트 (처리 완료)"""
        user_weekly_trend.is_processed = True
        user_weekly_trend.save()

        result = user_weekly_trend_admin.is_processed_colored(
            user_weekly_trend
        )
        assert "green" in result
        assert "✓" in result

    def test_is_processed_colored_false(
        self, user_weekly_trend_admin, user_weekly_trend: UserWeeklyTrend
    ):
        """is_processed_colored 메소드 테스트 (미처리)"""
        user_weekly_trend.is_processed = False
        user_weekly_trend.save()

        result = user_weekly_trend_admin.is_processed_colored(
            user_weekly_trend
        )
        assert "red" in result
        assert "✗" in result

    def test_processed_at_formatted_with_date(
        self, user_weekly_trend_admin, user_weekly_trend: UserWeeklyTrend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 있음)"""
        now = get_local_now()
        user_weekly_trend.processed_at = now
        user_weekly_trend.save()

        result = user_weekly_trend_admin.processed_at_formatted(
            user_weekly_trend
        )
        assert now.strftime("%Y-%m-%d %H:%M") == result

    def test_processed_at_formatted_no_date(
        self, user_weekly_trend_admin, user_weekly_trend: UserWeeklyTrend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 없음)"""
        user_weekly_trend.processed_at = None
        user_weekly_trend.save()

        result = user_weekly_trend_admin.processed_at_formatted(
            user_weekly_trend
        )
        assert result == "-"

    def test_mark_as_processed(
        self,
        user_weekly_trend_admin,
        user_weekly_trend: UserWeeklyTrend,
        request_factory,
    ):
        """mark_as_processed 메소드 테스트"""
        user_weekly_trend.is_processed = False
        user_weekly_trend.processed_at = None
        user_weekly_trend.save()

        with patch("utils.utils.get_local_now") as mock_now:
            mock_now.return_value = get_local_now()
            user_weekly_trend_admin.mark_as_processed(
                request_factory,
                user_weekly_trend.__class__.objects.filter(
                    pk=user_weekly_trend.pk
                ),
            )

        user_weekly_trend.refresh_from_db()
        assert user_weekly_trend.is_processed is True
        assert user_weekly_trend.processed_at is not None
