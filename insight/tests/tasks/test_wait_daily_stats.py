import urllib.error
import urllib.parse
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from insight.tasks import wait_daily_stats
from insight.tasks.wait_daily_stats import (
    fetch_today_success_runs,
    has_active_run,
    missing_sets,
    wait_for_daily_stats,
)

NOW = datetime(2026, 11, 23, 7, 5, tzinfo=ZoneInfo("Asia/Seoul"))


def stats_run(set_no: int, status: str = "completed") -> dict:
    return {"name": f"Daily Stats Batch (set{set_no})", "status": status}


def all_stats_runs() -> list[dict]:
    return [stats_run(n) for n in range(1, 21)]


class FakeClock:
    """sleep 한 만큼만 흐르는 가짜 시계"""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TestMissingSets:
    def test_returns_sorted_missing_set_numbers(self):
        """성공 run 이 없는 세트 번호만 오름차순으로 돌려준다"""
        runs = [stats_run(n) for n in range(20, 0, -1) if n not in (3, 17)]
        runs += [stats_run(1), {"name": "Weekly Analysis"}]

        assert missing_sets(runs) == [3, 17]


class TestFetchTodaySuccessRuns:
    def test_reads_next_pages_until_total_count(self, monkeypatch):
        """total_count 가 받은 수보다 크면 다음 쪽을 읽어 모두 모은다"""
        pages = {
            "1": {"total_count": 101, "workflow_runs": [stats_run(1)] * 100},
            "2": {"total_count": 101, "workflow_runs": [stats_run(2)]},
        }
        requested = []

        def fake_get_json(url):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            requested.append(query)
            return pages[query["page"][0]]

        monkeypatch.setattr(wait_daily_stats, "_get_json", fake_get_json)

        runs = fetch_today_success_runs(NOW)

        assert len(runs) == 101
        assert [q["page"] for q in requested] == [["1"], ["2"]]
        assert requested[0]["status"] == ["success"]
        assert requested[0]["created"] == [">=2026-11-23T00:00:00+09:00"]


class TestHasActiveRun:
    @pytest.mark.parametrize(
        "status", ["queued", "in_progress", "waiting", "pending"]
    )
    def test_unfinished_run_is_active(self, status):
        """끝나지 않은 run 이 있으면 True"""
        runs = [{"name": "Weekly Analysis", "status": status}]

        assert has_active_run(runs, "Weekly Analysis")

    def test_finished_or_other_workflow_is_not_active(self):
        """끝난 run 이나 다른 워크플로의 실행 중 run 은 보지 않는다"""
        runs = [
            {"name": "Weekly Analysis", "status": "completed"},
            {"name": "Weekly Newsletter", "status": "in_progress"},
        ]

        assert not has_active_run(runs, "Weekly Analysis")


class TestWaitForDailyStats:
    def test_returns_immediately_when_all_sets_done(self):
        """다 모였으면 기다리지 않고 빈 리스트"""
        clock = FakeClock()

        missing = wait_for_daily_stats(
            NOW, lambda now: all_stats_runs(), clock.sleep, clock, MagicMock()
        )

        assert missing == []
        assert clock.now == 0

    def test_returns_when_sets_complete_while_waiting(self):
        """기다리는 사이 다 모이면 그때 끝난다"""
        clock = FakeClock()
        responses = iter([all_stats_runs()[1:], all_stats_runs()])

        missing = wait_for_daily_stats(
            NOW,
            lambda now: next(responses),
            clock.sleep,
            clock,
            MagicMock(),
            timeout_sec=900,
            interval_sec=300,
        )

        assert missing == []
        assert clock.now == 300

    def test_times_out_with_warning(self):
        """제한 시간이 지나면 빠진 세트를 경고로 남기고 돌려준다"""
        clock = FakeClock()
        logger = MagicMock()
        runs = [run for run in all_stats_runs() if run != stats_run(5)]

        missing = wait_for_daily_stats(
            NOW,
            lambda now: runs,
            clock.sleep,
            clock,
            logger,
            timeout_sec=900,
            interval_sec=300,
        )

        assert missing == [5]
        assert clock.now <= 900
        assert [5] in logger.warning.call_args.args

    def test_fetch_errors_do_not_raise(self):
        """조회가 계속 실패해도 예외 없이 모든 세트를 빠진 것으로 돌려준다"""
        clock = FakeClock()
        logger = MagicMock()

        def failing_fetch(now):
            raise urllib.error.URLError("network down")

        missing = wait_for_daily_stats(
            NOW, failing_fetch, clock.sleep, clock, logger
        )

        assert missing == list(range(1, 21))
        assert list(range(1, 21)) in logger.warning.call_args.args
