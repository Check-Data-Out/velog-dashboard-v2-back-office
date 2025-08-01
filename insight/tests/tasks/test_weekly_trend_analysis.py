from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyTrendAnalyzer:
    @pytest.fixture
    def analyzer(self):
        """WeeklyTrendAnalyzer 인스턴스 생성"""
        from insight.tasks.weekly_trend_analysis import WeeklyTrendAnalyzer

        return WeeklyTrendAnalyzer(trending_limit=1)

    @pytest.fixture
    def mock_context(self):
        """VelogClient mock 포함된 context 객체 생성"""
        mock_user = MagicMock(username="tester")
        mock_post = MagicMock(
            id="abc123",
            title="test title",
            views=100,
            likes=10,
            user=mock_user,
            thumbnail="thumbnail",
            url_slug="test",
        )
        mock_detail = MagicMock(body="test content")

        mock_velog_client = AsyncMock()
        mock_velog_client.get_trending_posts.return_value = [mock_post]
        mock_velog_client.get_post.return_value = mock_detail

        mock_context = MagicMock()
        mock_context.velog_client = mock_velog_client
        mock_context.week_start.date.return_value = "2025-07-21"
        mock_context.week_end.date.return_value = "2025-07-27"
        mock_context.week_end = datetime(2025, 7, 27)

        return mock_context

    @pytest.fixture
    def trending_post_data(self):
        """LLM 분석용 TrendingPostData fixture"""
        from insight.tasks.weekly_trend_analysis import TrendingPostData

        mock_post = MagicMock(
            title="test",
            views=1,
            likes=2,
            user=MagicMock(username="tester"),
            thumbnail="thumbnail",
            url_slug="slug",
        )
        return TrendingPostData(post=mock_post, body="내용")

    async def test_fetch_data_success(self, analyzer, mock_context):
        """트렌딩 게시글의 본문 데이터 수집 성공 테스트"""
        with patch.object(analyzer, "logger") as mock_logger:
            result = await analyzer._fetch_data(mock_context)

        from insight.tasks.weekly_trend_analysis import TrendingPostData

        assert len(result) == 1
        assert isinstance(result[0], TrendingPostData)
        assert result[0].body == "test content"
        assert result[0].post.title == "test title"
        mock_logger.info.assert_called()

    async def test_fetch_data_when_fail_get_post_detail(
        self, analyzer, mock_context
    ):
        """게시글 본문 조회 실패 시, body 없이 기본 데이터로 대체되는지 테스트"""
        mock_context.velog_client.get_post.side_effect = Exception(
            "fetch error"
        )

        with patch.object(analyzer, "logger") as mock_logger:
            result = await analyzer._fetch_data(mock_context)

        assert len(result) == 1
        assert result[0].body == ""
        mock_logger.warning.assert_called()

    async def test_fetch_data_failure_with_empty_body(
        self, analyzer, mock_context
    ):
        """게시글 본문이 비었을 경우, warning 로그 출력 확인 테스트"""
        mock_context.velog_client.get_post.return_value.body = ""

        with patch.object(analyzer, "logger") as mock_logger:
            result = await analyzer._fetch_data(mock_context)

        assert result[0].body == ""
        mock_logger.warning.assert_called_with(
            "Post %s has empty body", "abc123"
        )

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
