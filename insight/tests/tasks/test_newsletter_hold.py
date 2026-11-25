from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from insight.models import REVIEW_NEEDS, REVIEW_READY, WeeklyTrend
from utils.utils import get_this_week_monday


@pytest.fixture
def newsletter_batch(mock_setup_django):
    from insight.tasks.weekly_newsletter_batch import WeeklyNewsletterBatch

    return WeeklyNewsletterBatch(ses_client=MagicMock())


@pytest.fixture
def this_week_end(monday):
    """이번 주 행의 종료일(지난 일요일)"""
    return get_this_week_monday(monday) - timedelta(days=1)


@pytest.mark.usefixtures("mock_setup_django", "monday")
class TestNewsletterHoldGate:
    def test_default_review_status_is_ready(
        self, db, newsletter_batch, this_week_end
    ):
        """신규 WeeklyTrend 의 검수 상태 기본값은 발송 가능(ready)."""
        end = this_week_end
        trend = WeeklyTrend.objects.create(
            week_start_date=end - timedelta(days=7),
            week_end_date=end,
            insight={},
        )
        assert trend.review_status == REVIEW_READY

    def test_default_trend_is_sent_without_approval(
        self, db, newsletter_batch, this_week_end
    ):
        """기본(ready) 주차는 승인 없이 그대로 발송 대상으로 선택된다."""
        end = this_week_end
        WeeklyTrend.objects.create(
            week_start_date=end - timedelta(days=7),
            week_end_date=end,
            insight={"x": "auto"},
        )
        selected = newsletter_batch._select_weekly_trend()
        assert selected is not None
        assert selected.insight == {"x": "auto"}

    def test_held_trend_is_not_selected(
        self, db, newsletter_batch, this_week_end
    ):
        """검수 보류(needs_review) 주차는 발송 대상에서 제외된다."""
        end = this_week_end
        WeeklyTrend.objects.create(
            week_start_date=end - timedelta(days=7),
            week_end_date=end,
            insight={"x": "held"},
            review_status=REVIEW_NEEDS,
        )
        assert newsletter_batch._select_weekly_trend() is None

    def test_new_ready_selected_over_old_held(
        self, db, newsletter_batch, this_week_end
    ):
        """묵은 보류 row 가 있어도 최신 ready 주차가 선택된다(데드락 방지)."""
        base = this_week_end
        WeeklyTrend.objects.create(
            week_start_date=base - timedelta(days=7),
            week_end_date=base,
            insight={"x": "old_held"},
            review_status=REVIEW_NEEDS,
        )
        WeeklyTrend.objects.create(
            week_start_date=base,
            week_end_date=base + timedelta(days=7),
            insight={"x": "new_ready"},
            review_status=REVIEW_READY,
        )
        selected = newsletter_batch._select_weekly_trend()
        assert selected is not None
        assert selected.insight == {"x": "new_ready"}
