from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from insight.models import REVIEW_NEEDS, REVIEW_READY, WeeklyTrend


@pytest.fixture
def newsletter_batch(mock_setup_django):
    from insight.tasks.weekly_newsletter_batch import WeeklyNewsletterBatch

    return WeeklyNewsletterBatch(ses_client=MagicMock())


@pytest.mark.usefixtures("mock_setup_django")
class TestNewsletterHoldGate:
    def test_default_review_status_is_ready(self, db, newsletter_batch):
        """신규 WeeklyTrend 의 검수 상태 기본값은 발송 가능(ready)."""
        end = newsletter_batch.before_a_week + timedelta(days=1)
        trend = WeeklyTrend.objects.create(
            week_start_date=end - timedelta(days=7),
            week_end_date=end,
            insight={},
        )
        assert trend.review_status == REVIEW_READY

    def test_held_trend_is_not_selected(self, db, newsletter_batch):
        """검수 보류(needs_review) 주차는 발송 대상에서 제외된다."""
        end = newsletter_batch.before_a_week + timedelta(days=1)
        WeeklyTrend.objects.create(
            week_start_date=end - timedelta(days=7),
            week_end_date=end,
            insight={"x": "held"},
            review_status=REVIEW_NEEDS,
        )
        assert newsletter_batch._select_weekly_trend() is None

    def test_new_ready_selected_over_old_held(self, db, newsletter_batch):
        """묵은 보류 row 가 있어도 최신 ready 주차가 선택된다(데드락 방지)."""
        base = newsletter_batch.before_a_week
        WeeklyTrend.objects.create(
            week_start_date=base - timedelta(days=6),
            week_end_date=base + timedelta(days=1),
            insight={"x": "old_held"},
            review_status=REVIEW_NEEDS,
        )
        WeeklyTrend.objects.create(
            week_start_date=base + timedelta(days=1),
            week_end_date=base + timedelta(days=8),
            insight={"x": "new_ready"},
            review_status=REVIEW_READY,
        )
        selected = newsletter_batch._select_weekly_trend()
        assert selected is not None
        assert selected["insight"] == {"x": "new_ready"}
