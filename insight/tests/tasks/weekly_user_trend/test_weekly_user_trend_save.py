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

        await analyzer_user._save_results([mock_result], mock_context)

        mock_create.assert_called_once()
