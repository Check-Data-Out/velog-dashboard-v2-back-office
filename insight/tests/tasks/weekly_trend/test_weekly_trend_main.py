from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import async_to_sync

from insight.models import WeeklyTrend
from utils.utils import get_this_week_monday

SKIP_MARKER = "weekly_trend_analysis.skipped"
RESULT_FILE = "weekly_analysis_result.txt"


@pytest.fixture
def weekly_trend_main(mock_setup_django):
    # 모듈 맨 위의 import setup_django 를 흉내 낸 뒤에만 불러올 수 있다
    from insight.tasks.weekly_trend_analysis import main

    return main


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """결과 파일과 표시 파일을 임시 폴더에 쓴다"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def mock_velog_client_cls(mock_post, mock_post_detail):
    """분석 컨텍스트가 만드는 VelogClient"""
    with patch("insight.tasks.base_analysis.VelogClient") as client_cls:
        velog_client = AsyncMock()
        velog_client.get_trending_posts.return_value = [mock_post]
        velog_client.get_post.return_value = mock_post_detail
        client_cls.get_client.return_value = velog_client
        yield client_cls


@pytest.fixture
def mock_llm(sample_weekly_trend_insight):
    with patch(
        "insight.tasks.weekly_trend_analysis.analyze_trending_posts",
        return_value=sample_weekly_trend_insight.to_json_dict(),
    ) as llm:
        yield llm


def create_weekly_trend(weeks_ago: int) -> WeeklyTrend:
    """weeks_ago 주 전 분석 행. 0 이면 이번 주(종료일이 지난 일요일)"""
    week_end = get_this_week_monday() - timedelta(days=1 + 7 * weeks_ago)
    return WeeklyTrend.objects.create(
        week_start_date=week_end - timedelta(days=6),
        week_end_date=week_end,
    )


@pytest.mark.django_db
class TestWeeklyTrendMain:
    def test_skips_without_velog_and_llm_when_this_week_exists(
        self, weekly_trend_main, work_dir, mock_velog_client_cls, mock_llm
    ):
        """이번 주 결과가 있으면 velog·LLM 을 부르지 않고 건너뜀 표시를 남긴다"""
        create_weekly_trend(weeks_ago=0)

        exit_code = async_to_sync(weekly_trend_main)()

        assert exit_code == 0
        mock_velog_client_cls.get_client.assert_not_called()
        mock_llm.assert_not_called()
        assert (work_dir / SKIP_MARKER).exists()
        assert "건너뜀" in (work_dir / RESULT_FILE).read_text()
        assert WeeklyTrend.objects.count() == 1

    def test_analyzes_when_only_last_week_exists(
        self, weekly_trend_main, work_dir, mock_velog_client_cls, mock_llm
    ):
        """지난주 결과만 있으면 분석하고, 지난 실행의 건너뜀 표시를 지운다"""
        create_weekly_trend(weeks_ago=1)
        Path(work_dir / SKIP_MARKER).touch()

        exit_code = async_to_sync(weekly_trend_main)()

        assert exit_code == 0
        mock_llm.assert_called_once()
        assert not (work_dir / SKIP_MARKER).exists()
        assert WeeklyTrend.objects.this_week().count() == 1
        session = mock_velog_client_cls.get_client.call_args.kwargs["session"]
        assert session.closed

    def test_closes_session_when_analysis_fails(
        self, weekly_trend_main, work_dir, mock_velog_client_cls, mock_llm
    ):
        """분석이 실패해도 컨텍스트가 연 aiohttp 세션을 닫는다"""
        velog_client = mock_velog_client_cls.get_client.return_value
        velog_client.get_trending_posts.side_effect = Exception("velog down")

        exit_code = async_to_sync(weekly_trend_main)()

        assert exit_code == 1
        session = mock_velog_client_cls.get_client.call_args.kwargs["session"]
        assert session.closed
