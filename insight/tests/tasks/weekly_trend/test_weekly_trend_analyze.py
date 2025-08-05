from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyTrendAnalyze:
    @patch("insight.tasks.weekly_trend_analysis.analyze_trending_posts")
    async def test_analyze_data_success(
        self, mock_llm, analyzer, trending_post_data
    ):
        """LLM 분석 성공 테스트"""
        mock_llm.return_value = {
            "trending_summary": [
                {"summary": "요약", "key_points": ["a", "b"]}
            ],
            "trend_analysis": {
                "hot_keywords": ["python"],
                "title_trends": "트렌드",
                "content_trends": "내용 트렌드",
                "insights": "인사이트",
            },
        }

        context = MagicMock()
        with patch.object(analyzer, "logger") as mock_logger:
            result = await analyzer._analyze_data(
                [trending_post_data], context
            )

        assert len(result) == 1
        insight = result[0]
        assert insight.trend_analysis.hot_keywords == ["python"]
        assert insight.trending_summary[0].summary == "요약"
        mock_logger.info.assert_called()

    @patch("insight.tasks.weekly_trend_analysis.analyze_trending_posts")
    async def test_analyze_data_with_summary_length_mismatch_fallback(
        self, mock_llm, analyzer, trending_post_data
    ):
        """LLM이 반환한 요약 개수가 원본보다 적을 때, 누락된 항목이 fallback 처리되는지 테스트"""
        mock_llm.return_value = {
            "trending_summary": [{"summary": "요약", "key_points": ["a"]}],
            "trend_analysis": {
                "hot_keywords": [],
                "title_trends": "",
                "content_trends": "",
                "insights": "",
            },
        }

        mock_context = MagicMock()
        with patch.object(analyzer, "logger") as mock_logger:
            result = await analyzer._analyze_data(
                [trending_post_data, trending_post_data], mock_context
            )
            mock_logger.info.assert_called()

        assert len(result[0].trending_summary) == 2

    @patch("insight.tasks.weekly_trend_analysis.analyze_trending_posts")
    async def test_analyze_data_failure(
        self, mock_llm, analyzer, trending_post_data
    ):
        """LLM 분석 중 예외 발생 시, 예외가 로깅되고 다시 전파되는지 테스트"""
        mock_llm.side_effect = Exception("LLM Error")

        with patch.object(analyzer, "logger") as mock_logger:
            with pytest.raises(Exception):
                await analyzer._analyze_data([trending_post_data], MagicMock())
            mock_logger.error.assert_called()
