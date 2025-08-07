from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyUserTrendSave:
    @patch(
        "insight.tasks.weekly_user_trend_analysis.UserWeeklyTrend.objects.create"
    )
    async def test_save_results_success(
        self,
        mock_create,
        analyzer_user,
        mock_context,
        sample_weekly_user_trend_insight,
    ):
        """사용자 게시글 분석 결과 저장 성공 테스트"""
        mock_result = {
            "user_id": 1,
            "insight": MagicMock(
                to_dict=lambda: sample_weekly_user_trend_insight.to_dict()
            ),
        }

        with patch.object(analyzer_user, "logger") as mock_logger:
            await analyzer_user._save_results([mock_result], mock_context)

            mock_create.assert_called_once()
            mock_logger.info.assert_called()

    @patch(
        "insight.tasks.weekly_user_trend_analysis.UserWeeklyTrend.objects.create",
        side_effect=[Exception("fail"), None],
    )
    async def test_save_results_continues_on_partial_failure(
        self,
        mock_create,
        analyzer_user,
        mock_context,
        sample_weekly_user_trend_insight,
    ):
        """분석 결과 중 일부 저장 실패가 발생해도 나머지 결과 저장이 계속 진행되는지 테스트"""
        result1 = {
            "user_id": 1,
            "insight": MagicMock(
                to_dict=lambda: sample_weekly_user_trend_insight.to_dict()
            ),
        }
        result2 = {
            "user_id": 2,
            "insight": MagicMock(
                to_dict=lambda: sample_weekly_user_trend_insight.to_dict()
            ),
        }

        with patch.object(analyzer_user, "logger") as mock_logger:
            await analyzer_user._save_results([result1, result2], mock_context)

            assert mock_create.call_count == 2
            mock_logger.error.assert_called_once()
            mock_logger.info.assert_called()
