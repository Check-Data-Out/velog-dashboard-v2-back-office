from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyTrendSave:
    @patch("insight.tasks.weekly_trend_analysis.WeeklyTrend.objects.create")
    async def test_save_results_success(
        self, mock_create, analyzer, mock_context
    ):
        """분석 결과 저장 성공 테스트"""
        trending_item = MagicMock()
        trending_item.to_dict.return_value = {"title": "test"}

        trend_analysis = MagicMock()
        trend_analysis.to_dict.return_value = {"insights": "Good"}

        result = MagicMock(
            trending_summary=[trending_item], trend_analysis=trend_analysis
        )

        with patch.object(analyzer, "logger") as mock_logger:
            await analyzer._save_results([result], mock_context)

        mock_create.assert_called_once_with(
            week_start_date="2025-07-21",
            week_end_date=date(2025, 7, 27),
            insight={
                "trending_summary": [{"title": "test"}],
                "trend_analysis": {"insights": "Good"},
            },
            is_processed=False,
            processed_at=datetime(2025, 7, 27),
        )
        mock_logger.info.assert_called()

    @patch(
        "insight.tasks.weekly_trend_analysis.WeeklyTrend.objects.create",
        side_effect=Exception("DB error"),
    )
    async def test_save_results_failure(
        self, mock_create, analyzer, mock_context
    ):
        """DB 저장 중 예외 발생 시, 로그 출력 및 예외 전파되는지 테스트"""
        result = MagicMock(
            trending_summary=[MagicMock(to_dict=lambda: {"title": "test"})],
            trend_analysis=MagicMock(to_dict=lambda: {"insights": "fail"}),
        )

        with patch.object(analyzer, "logger") as mock_logger:
            with pytest.raises(Exception):
                await analyzer._save_results([result], mock_context)
            mock_logger.error.assert_called()

    async def test_save_results_when_results_empty(
        self, analyzer, mock_context
    ):
        """분석 결과가 없을 경우, DB 저장 로직이 호출되지 않는지 테스트"""
        with patch(
            "insight.tasks.weekly_trend_analysis.WeeklyTrend.objects.create"
        ) as mock_create:
            await analyzer._save_results([], mock_context)
            mock_create.assert_not_called()
