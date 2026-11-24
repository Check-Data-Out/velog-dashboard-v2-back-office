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

    def test_stops_reading_pages_when_all_sets_are_found(self, monkeypatch):
        """최신순으로 읽다가 20세트를 다 찾으면 남은 쪽은 읽지 않는다"""
        requested = []

        def fake_get_json(url):
            requested.append(url)
            return {
                "total_count": 250,
                "workflow_runs": all_stats_runs() + [stats_run(1)] * 80,
            }

        monkeypatch.setattr(wait_daily_stats, "_get_json", fake_get_json)

        runs = fetch_today_success_runs(NOW)

        assert missing_sets(runs) == []
        assert len(requested) == 1


class TestHasActiveRun:
    def test_unfinished_run_is_active(self):
        """예약·수동으로 뜬 끝나지 않은 run 이 있으면 True"""
        runs = [
            {
                "name": "Weekly Analysis",
                "event": "schedule",
                "status": "in_progress",
            }
        ]

        assert has_active_run(runs, "Weekly Analysis")

    @pytest.mark.parametrize(
        "run",
        [
            {
                "name": "Weekly Analysis",
                "event": "schedule",
                "status": "completed",
            },
            {
                "name": "Weekly Newsletter",
                "event": "schedule",
                "status": "in_progress",
            },
            {
                "name": "Weekly Analysis",
                "event": "pull_request",
                "status": "in_progress",
            },
        ],
        ids=["finished", "other_workflow", "other_event"],
    )
    def test_finished_other_workflow_or_other_event_is_not_active(self, run):
        """끝난 run, 다른 워크플로의 run, 예약·수동이 아닌 이벤트(fork PR 등)의 run 은 보지 않는다"""
        assert not has_active_run([run], "Weekly Analysis")


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

    def test_times_out_with_missing_sets(self):
        """제한 시간이 지나면 기다림을 멈추고 빠진 세트를 돌려준다"""
        clock = FakeClock()
        runs = [run for run in all_stats_runs() if run != stats_run(5)]

        missing = wait_for_daily_stats(
            NOW,
            lambda now: runs,
            clock.sleep,
            clock,
            MagicMock(),
            timeout_sec=900,
            interval_sec=300,
        )

        assert missing == [5]
        assert clock.now <= 900

    def test_fetch_errors_do_not_raise(self):
        """조회가 계속 실패해도 예외 없이 모든 세트를 빠진 것으로 돌려준다"""
        clock = FakeClock()

        def failing_fetch(now):
            raise urllib.error.URLError("network down")

        missing = wait_for_daily_stats(
            NOW, failing_fetch, clock.sleep, clock, MagicMock()
        )

        assert missing == list(range(1, 21))

    def test_retries_fetch_error_sooner_than_interval(self):
        """조회가 실패하면 조회 간격이 아니라 30초 뒤 다시 본다"""
        clock = FakeClock()
        responses = iter([urllib.error.URLError("network down")])

        def fetch_once_failing(now):
            error = next(responses, None)
            if error:
                raise error
            return all_stats_runs()

        missing = wait_for_daily_stats(
            NOW,
            fetch_once_failing,
            clock.sleep,
            clock,
            MagicMock(),
            interval_sec=300,
        )

        assert missing == []
        assert clock.now == 30
