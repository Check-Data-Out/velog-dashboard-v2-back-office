"""cleanup_old_stats management command 테스트."""

from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import ProgrammingError
from django.utils import timezone

from posts.management.commands.cleanup_old_stats import Command
from posts.models import PostDailyStatistics

DROP_CHUNKS_HELPER = "posts.management.commands.cleanup_old_stats.Command._drop_chunks_and_get_cutoff"
ORM_FALLBACK_HELPER = (
    "posts.management.commands.cleanup_old_stats.Command._orm_fallback"
)


def _mock_cursor(fetchall_return=None, fetchone_return=None):
    """connection.cursor() 컨텍스트 매니저 mock 헬퍼."""
    fake_cm = MagicMock()
    fake_cursor = fake_cm.__enter__.return_value
    fake_cursor.fetchall.return_value = fetchall_return or []
    fake_cursor.fetchone.return_value = fetchone_return or (
        timezone.now() - timedelta(days=180),
    )
    return fake_cm, fake_cursor


@pytest.fixture(autouse=True)
def quiet_external_calls(monkeypatch):
    """Slack/Redis 외부 호출 차단. notify mock 을 반환해 검증 가능."""
    notify_mock = MagicMock()
    monkeypatch.setattr(
        "posts.management.commands.cleanup_old_stats.get_redis_client",
        lambda: None,
    )
    monkeypatch.setattr(
        "posts.management.commands.cleanup_old_stats.notify_ops",
        notify_mock,
    )
    return notify_mock


@pytest.mark.parametrize(
    "args",
    [
        ["--retention-months", "0"],
        ["--retention-months", "-1"],
        ["--chunk", "0"],
        ["--chunk", "-5"],
    ],
)
def test_invalid_args_raise_command_error(args):
    with pytest.raises(CommandError):
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
    cutoff = timezone.now() - timedelta(days=180)
    with (
        patch(
            "posts.management.commands.cleanup_old_stats.timezone.now",
            return_value=utc_dt,
        ),
        patch(DROP_CHUNKS_HELPER, return_value=(0, cutoff)),
        patch(ORM_FALLBACK_HELPER, return_value=0),
    ):
        out = StringIO()
        call_command("cleanup_old_stats", stdout=out)
        skipped = "skipping" in out.getvalue().lower()
        assert skipped is should_skip


def test_force_bypasses_day_guard():
    # KST 16일 — guard 라면 skip 이지만 --force 는 우회해야 함
    cutoff = timezone.now() - timedelta(days=180)
    with (
        patch(
            "posts.management.commands.cleanup_old_stats.timezone.now",
            return_value=datetime(2026, 5, 15, 19, 0, tzinfo=UTC),
        ),
        patch(DROP_CHUNKS_HELPER, return_value=(0, cutoff)),
        patch(ORM_FALLBACK_HELPER, return_value=0),
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


@pytest.mark.django_db
def test_drop_chunks_helper_uses_ts2_signature_and_statement_timeout():
    """helper 단위 검증 — call_command 거치지 않고 SQL 토큰만 확인."""
    fake_cm, fake_cursor = _mock_cursor()
    with patch(
        "posts.management.commands.cleanup_old_stats.connection.cursor",
        return_value=fake_cm,
    ):
        Command()._drop_chunks_and_get_cutoff(6)
    executed = [str(c.args[0]) for c in fake_cursor.execute.mock_calls]
    assert any("drop_chunks" in s and "older_than" in s for s in executed)
    assert any("statement_timeout" in s for s in executed)


@pytest.mark.django_db
def test_orm_fallback_deletes_rows_below_cutoff(post_stats_factory):
    """helper mock + 실제 ORM fallback 동작 검증."""
    old_stats = post_stats_factory(date=timezone.now() - timedelta(days=200))
    new_stats = post_stats_factory(date=timezone.now() - timedelta(days=30))
    cutoff = timezone.now() - timedelta(days=180)
    with patch(DROP_CHUNKS_HELPER, return_value=(0, cutoff)):
        call_command("cleanup_old_stats", "--force")
    assert not PostDailyStatistics.objects.filter(pk=old_stats.pk).exists()
    assert PostDailyStatistics.objects.filter(pk=new_stats.pk).exists()


@pytest.mark.django_db
def test_empty_table_runs_without_error():
    cutoff = timezone.now() - timedelta(days=180)
    with patch(DROP_CHUNKS_HELPER, return_value=(0, cutoff)):
        call_command("cleanup_old_stats", "--force")


@pytest.mark.django_db
def test_second_run_is_noop_after_cleanup(post_stats_factory):
    """1차 실행 후 데이터 정리됨 → 2차 실행은 빈 ORM 폴백으로 정상 종료."""
    old_stats = post_stats_factory(date=timezone.now() - timedelta(days=200))
    cutoff = timezone.now() - timedelta(days=180)
    with patch(DROP_CHUNKS_HELPER, return_value=(0, cutoff)):
        call_command("cleanup_old_stats", "--force")
        assert not PostDailyStatistics.objects.filter(pk=old_stats.pk).exists()
        # 2차 실행 — orm count = 0, exception 없이 종료
        call_command("cleanup_old_stats", "--force")


def test_drop_chunks_error_raises_command_error_and_notifies_failure(
    quiet_external_calls,
):
    with patch(
        DROP_CHUNKS_HELPER,
        side_effect=ProgrammingError(
            "function drop_chunks(...) does not exist"
        ),
    ):
        with pytest.raises(CommandError):
            call_command("cleanup_old_stats", "--force")
    assert quiet_external_calls.called
    assert "실패" in quiet_external_calls.call_args.kwargs["text"]


@pytest.mark.django_db
def test_notify_ops_called_on_success(quiet_external_calls):
    cutoff = timezone.now() - timedelta(days=180)
    with patch(DROP_CHUNKS_HELPER, return_value=(0, cutoff)):
        call_command("cleanup_old_stats", "--force")
    assert quiet_external_calls.called
    assert (
        quiet_external_calls.call_args.kwargs["cooldown_key"]
        == "cleanup-old-stats"
    )
    assert "정리 완료" in quiet_external_calls.call_args.kwargs["text"]


@pytest.mark.django_db
def test_notify_ops_not_called_in_dry_run(
    post_stats_factory, quiet_external_calls
):
    post_stats_factory(date=timezone.now() - timedelta(days=200))
    call_command("cleanup_old_stats", "--dry-run", "--force")
    assert not quiet_external_calls.called


def test_default_retention_months_is_6():
    """AC-2 — `--retention-months` 기본값 6."""
    cmd = Command()
    parser = cmd.create_parser("manage.py", "cleanup_old_stats")
    ns = parser.parse_args([])
    assert ns.retention_months == 6


@pytest.mark.django_db
def test_orm_fallback_aborts_when_delete_returns_zero(caplog):
    """AC-10 zero-delete guard — delete 가 0 반환 시 break + warning."""
    cmd = Command()
    cutoff = timezone.now() - timedelta(days=180)
    with patch(
        "posts.management.commands.cleanup_old_stats.PostDailyStatistics.objects"
    ) as mock_objects:
        # filter().count() = 5, filter().values_list()[:N] = [1..5], filter().delete() = (0, {})
        mock_qs = MagicMock()
        mock_qs.count.return_value = 5
        mock_qs.values_list.return_value.__getitem__.return_value = [
            1,
            2,
            3,
            4,
            5,
        ]
        mock_qs.delete.return_value = (0, {})
        mock_objects.filter.return_value = mock_qs
        with caplog.at_level(
            "WARNING", logger="posts.management.commands.cleanup_old_stats"
        ):
            result = cmd._orm_fallback(cutoff, chunk=5)
    assert result == 0
    assert any("delete returned 0" in r.getMessage() for r in caplog.records)
    # delete 가 1번만 호출되고 break 되어야 함
    assert mock_qs.delete.call_count == 1


@pytest.mark.django_db
def test_redis_unavailable_does_not_fail_batch(monkeypatch, caplog):
    """get_redis_client 가 예외를 raise 해도 배치는 정상 종료."""
    monkeypatch.setattr(
        "posts.management.commands.cleanup_old_stats.get_redis_client",
        MagicMock(side_effect=ConnectionError("redis down")),
    )
    cutoff = timezone.now() - timedelta(days=180)
    with (
        patch(DROP_CHUNKS_HELPER, return_value=(0, cutoff)),
        caplog.at_level(
            "WARNING", logger="posts.management.commands.cleanup_old_stats"
        ),
    ):
        call_command("cleanup_old_stats", "--force")
    assert any("redis" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.django_db
def test_summary_log_contains_key_fields(caplog):
    cutoff = timezone.now() - timedelta(days=180)
    with (
        patch(DROP_CHUNKS_HELPER, return_value=(3, cutoff)),
        caplog.at_level(
            "INFO", logger="posts.management.commands.cleanup_old_stats"
        ),
    ):
        call_command("cleanup_old_stats", "--force")
    log_text = " ".join(r.getMessage() for r in caplog.records)
    for token in ("cutoff=", "dropped_chunks=", "orm_deleted="):
        assert token in log_text, f"missing token: {token} in {log_text!r}"
