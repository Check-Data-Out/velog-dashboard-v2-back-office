from unittest.mock import MagicMock, patch

import pytest

from insight.models import WeeklyUserStats


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyUserTrendAnalyze:
    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch(
        "insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects"
    )
    async def test_calculate_user_weekly_total_stats_success(
        self, mock_stats, mock_posts, analyzer_user, mock_context
    ):
        """사용자 주간 전체 통계 계산 성공 테스트"""
        mock_posts.filter.return_value.values_list.return_value = [1, 2]
        mock_posts.filter.return_value.count.return_value = 1
        mock_stats.filter.return_value.values.return_value = [
            {
                "post_id": 1,
                "date": mock_context.week_start,
                "daily_view_count": 10,
                "daily_like_count": 5,
            },
            {
                "post_id": 1,
                "date": mock_context.week_end,
                "daily_view_count": 15,
                "daily_like_count": 10,
            },
        ]

        stats = await analyzer_user._calculate_user_weekly_total_stats(
            1, mock_context
        )
        assert isinstance(stats, WeeklyUserStats)
        assert stats.posts == 1
        assert stats.views == 5
        assert stats.likes == 5
        assert stats.new_posts == 1

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch(
        "insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects"
    )
    async def test_calculate_user_weekly_total_stats_missing_stats(
        self, mock_stats, mock_posts, analyzer_user, mock_context
    ):
        """통계가 누락된 경우, 조회수와 좋아요 수가 0으로 처리되는지 테스트"""
        mock_posts.filter.return_value.values_list.return_value = [1]
        mock_posts.filter.return_value.count.return_value = 1
        mock_stats.filter.return_value.values.return_value = []

        stats = await analyzer_user._calculate_user_weekly_total_stats(
            1, mock_context
        )
        assert stats.views == 0
        assert stats.likes == 0

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch(
        "insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects"
    )
    async def test_calculate_user_weekly_total_stats_ignores_negative_diff(
        self, mock_stats, mock_posts, analyzer_user, mock_context
    ):
        """조회수나 좋아요 수가 감소한 경우, 0으로 처리하여 음수 결과를 방지하는지 테스트"""
        mock_posts.filter.return_value.values_list.return_value = [1]
        mock_posts.filter.return_value.count.return_value = 1
        mock_stats.filter.return_value.values.return_value = [
            {
                "post_id": 1,
                "date": mock_context.week_start,
                "daily_view_count": 200,
                "daily_like_count": 100,
            },
            {
                "post_id": 1,
                "date": mock_context.week_end,
                "daily_view_count": 180,
                "daily_like_count": 90,
            },
        ]

        stats = await analyzer_user._calculate_user_weekly_total_stats(
            1, mock_context
        )
        assert stats.views == 0
        assert stats.likes == 0

    @patch("insight.tasks.weekly_user_trend_analysis.analyze_user_posts")
    async def test_analyze_user_posts_success(
        self,
        mock_analyze,
        analyzer_user,
        sample_trend_analysis,
        sample_trending_items,
    ):
        """사용자 게시글 분석 성공 테스트"""
        mock_post = MagicMock(
            title="test", thumbnail="", url_slug="slug", body="내용"
        )
        mock_analyze.return_value = {
            "trending_summary": [sample_trending_items[0].to_dict()],
            "trend_analysis": sample_trend_analysis.to_dict(),
        }

        (
            trending_items,
            trend_analysis,
        ) = await analyzer_user._analyze_user_posts_with_llm(
            [mock_post], "user"
        )

        assert len(trending_items) == 1
        assert trend_analysis is not None
        assert (
            trend_analysis.hot_keywords == sample_trend_analysis.hot_keywords
        )

    @patch(
        "insight.tasks.weekly_user_trend_analysis.analyze_user_posts",
        side_effect=Exception("LLM 실패"),
    )
    async def test_analyze_user_posts_failure_returns_fallback(
        self, mock_llm, analyzer_user
    ):
        """LLM 분석 실패 시, [분석 실패] 요약과 None 분석 결과를 반환하는지 테스트"""
        mock_post = MagicMock(
            title="post1", thumbnail="", url_slug="slug", body="내용"
        )
        items, trend = await analyzer_user._analyze_user_posts_with_llm(
            [mock_post], "tester"
        )

        assert len(items) == 1
        assert items[0].summary == "[분석 실패]"
        assert trend is None

    @patch(
        "insight.tasks.weekly_user_trend_analysis.UserWeeklyAnalyzer._create_user_reminder"
    )
    async def test_analyze_user_data_without_new_posts_creates_reminder(
        self, mock_reminder, analyzer_user, mock_context
    ):
        """신규 게시글이 없는 사용자의 경우, 리마인더 생성 로직이 동작하는지 테스트"""
        user_data = MagicMock()
        user_data.user_id = 1
        user_data.username = "tester"
        user_data.weekly_new_posts = []
        user_data.weekly_total_stats = WeeklyUserStats(
            posts=0, new_posts=0, views=0, likes=0
        )

        mock_reminder.return_value = MagicMock(title="최근 글", days_ago=5)

        insight = await analyzer_user._analyze_user_data(
            user_data, mock_context
        )
        assert insight.user_weekly_reminder.title == "최근 글"
        mock_reminder.assert_called_once()
