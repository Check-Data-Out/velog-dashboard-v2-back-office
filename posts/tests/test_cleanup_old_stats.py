"""cleanup_old_stats management command 테스트."""

from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from posts.models import PostDailyStatistics


@pytest.mark.parametrize(
    "args",
    [
        ["--retention-months", "0"],
        ["--retention-months", "-1"],
        ["--chunk", "0"],
        ["--chunk", "-5"],
    ],
)
def test_invalid_args_raise_system_exit(args):
    with pytest.raises(SystemExit):
        call_command("cleanup_old_stats", *args)


@pytest.mark.parametrize(
    "utc_dt, should_skip",
    [
        # KST 16일 03:00 → skip
        (datetime(2026, 5, 15, 19, 0, tzinfo=UTC), True),
        # KST 1일 03:00 → 통과 (workflow_dispatch 시나리오)
        (datetime(2026, 5, 31, 18, 0, tzinfo=UTC), False),
        # KST 2일 04:00 (cron 발화) → 통과
        (datetime(2026, 6, 1, 19, 0, tzinfo=UTC), False),
        # KST 3일 03:00 → skip
        (datetime(2026, 6, 2, 18, 0, tzinfo=UTC), True),
    ],
)
def test_day_guard_only_passes_on_kst_day_1_or_2(utc_dt, should_skip):
    with patch(
        "posts.management.commands.cleanup_old_stats.timezone.now",
        return_value=utc_dt,
    ):
        out = StringIO()
        call_command("cleanup_old_stats", stdout=out)
        skipped = "skipping" in out.getvalue().lower()
        assert skipped is should_skip


def test_force_bypasses_day_guard():
    # KST 16일 — guard 라면 skip 이지만 --force 는 우회해야 함
    with patch(
        "posts.management.commands.cleanup_old_stats.timezone.now",
        return_value=datetime(2026, 5, 15, 19, 0, tzinfo=UTC),
    ):
        out = StringIO()
        call_command("cleanup_old_stats", "--force", stdout=out)
        assert "skipping" not in out.getvalue().lower()


@pytest.mark.django_db
def test_dry_run_reports_summary_and_keeps_rows(post_stats_factory):
    old_stats = post_stats_factory(date=timezone.now() - timedelta(days=200))
    out = StringIO()
    call_command("cleanup_old_stats", "--dry-run", "--force", stdout=out)
    output = out.getvalue()
    assert "cutoff=" in output
    assert "chunks=" in output
    assert "rows~=" in output
    # dry-run 은 실제 행을 건드리지 않아야 함 (drop_chunks 미호출의 implicit 검증)
    assert PostDailyStatistics.objects.filter(pk=old_stats.pk).exists()
