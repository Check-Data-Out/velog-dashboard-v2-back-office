from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from insight.models import WeeklyUserStats


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestUserWeeklyAnalyzer:
    @pytest.fixture
    def analyzer(self):
        from insight.tasks.weekly_user_trend_analysis import UserWeeklyAnalyzer

        return UserWeeklyAnalyzer()

    @pytest.fixture
    def mock_context(self):
        mock_context = MagicMock()
        mock_week_start = MagicMock()
        mock_week_end = MagicMock()

        mock_context.week_start = mock_week_start
        mock_context.week_end = mock_week_end
        mock_context.velog_client = AsyncMock()
        return mock_context

    async def test_check_user_token_validity_success(
        self, analyzer, mock_context
    ):
        """사용자 토큰 유효성 확인 성공 테스트"""
        with (
            patch(
                "insight.tasks.weekly_user_trend_analysis.Post.objects"
            ) as mock_posts,
            patch(
                "insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects"
            ) as mock_stats,
        ):
            mock_posts.filter.return_value.values_list.return_value = [1, 2]
            mock_stats.filter.return_value.count.return_value = 2

            is_valid = await analyzer._check_user_token_validity(
                1, mock_context
            )
            assert is_valid is True

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    async def test_check_user_token_validity_with_no_posts(
        self, mock_posts, analyzer, mock_context
    ):
        """게시글이 없는 경우에도 토큰을 유효하다고 판단하는지 테스트"""
        mock_posts.filter.return_value.values_list.return_value = []
        is_valid = await analyzer._check_user_token_validity(1, mock_context)
        assert is_valid is True

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch("insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects")
    async def test_check_user_token_validity_failure(
        self, mock_stats, mock_posts, analyzer, mock_context
    ):
        """게시글은 있으나 통계가 없을 경우, 사용자 토큰을 무효하다고 판단하는지 테스트"""
        mock_posts.filter.return_value.values_list.return_value = [1]
        mock_stats.filter.return_value.count.return_value = 0

        with patch.object(analyzer, "logger") as mock_logger:
            is_valid = await analyzer._check_user_token_validity(
                1, mock_context
            )
            assert is_valid is False
            mock_logger.warning.assert_called_once()

    async def test_token_expired_error_by_today_stats_missing(
        self, analyzer, mock_context
    ):
        """오늘자 통계가 없을 경우 TokenExpiredError 발생 여부 테스트"""
        with (
            patch("insight.tasks.weekly_user_trend_analysis.Post.objects") as mock_posts,
            patch("insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects") as mock_stats
        ):
            mock_posts.filter.return_value.values_list.return_value = [123]
            mock_stats.filter.return_value.count.return_value = 0

            with patch.object(analyzer, "logger") as mock_logger:
                is_valid = await analyzer._check_user_token_validity(123, mock_context)
                assert is_valid is False
                mock_logger.warning.assert_called_with(
                    "User %s token expired - no today stats", 123
                )

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch("insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects")
    async def test_calculate_user_weekly_total_stats_success(
        self, mock_stats, mock_posts, analyzer, mock_context
    ):
        """사용자 주간 전체 통계 계산 성공 테스트"""
        mock_posts.filter.side_effect = [
            MagicMock(values_list=MagicMock(return_value=[1, 2])),
            MagicMock(count=MagicMock(return_value=1)),
        ]
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

        stats = await analyzer._calculate_user_weekly_total_stats(
            1, mock_context
        )
        assert isinstance(stats, WeeklyUserStats)
        assert stats.posts == 1
        assert stats.views == 5
        assert stats.likes == 5
        assert stats.new_posts == 1

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch("insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects")
    async def test_calculate_user_weekly_total_stats_missing_stats(
        self, mock_stats, mock_posts, analyzer, mock_context
    ):
        """통계가 누락된 경우, 조회수와 좋아요 수가 0으로 처리되는지 테스트"""
        mock_posts.filter.side_effect = [
            MagicMock(values_list=MagicMock(return_value=[1])),
            MagicMock(count=MagicMock(return_value=1)),
        ]
        mock_stats.filter.return_value.values.return_value = []

        stats = await analyzer._calculate_user_weekly_total_stats(
            1, mock_context
        )
        assert stats.views == 0
        assert stats.likes == 0

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch("insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects")
    async def test_calculate_user_weekly_total_stats_ignores_negative_diff(
        self, mock_stats, mock_posts, analyzer, mock_context
    ):
        """조회수나 좋아요 수가 감소한 경우, 0으로 처리하여 음수 결과를 방지하는지 테스트"""
        mock_posts.filter.side_effect = [
            MagicMock(values_list=MagicMock(return_value=[1])),
            MagicMock(count=MagicMock(return_value=1)),
        ]
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

        stats = await analyzer._calculate_user_weekly_total_stats(
            1, mock_context
        )
        assert stats.views == 0
        assert stats.likes == 0

    @patch("insight.tasks.weekly_user_trend_analysis.analyze_user_posts")
    async def test_analyze_user_posts_success(self, mock_analyze, analyzer):
        """사용자 게시글 분석 성공 테스트"""
        mock_post = MagicMock(
            title="test", thumbnail="", url_slug="slug", body="내용"
        )
        mock_analyze.return_value = {
            "trending_summary": [
                {"title": "test", "summary": "요약", "key_points": ["a", "b"]}
            ],
            "trend_analysis": {
                "hot_keywords": ["python"],
                "title_trends": "트렌드",
                "content_trends": "내용트렌드",
                "insights": "인사이트",
            },
        }

        (
            trending_items,
            trend_analysis,
        ) = await analyzer._analyze_user_posts_with_llm([mock_post], "user")

        assert len(trending_items) == 1
        assert trend_analysis.hot_keywords == ["python"]

    @patch(
        "insight.tasks.weekly_user_trend_analysis.analyze_user_posts",
        side_effect=Exception("LLM 실패"),
    )
    async def test_analyze_user_posts_failure_returns_fallback(
        self, mock_llm, analyzer
    ):
        """LLM 분석 실패 시, [분석 실패] 요약과 None 분석 결과를 반환하는지 테스트"""
        mock_post = MagicMock(
            title="post1", thumbnail="", url_slug="slug", body="내용"
        )
        items, trend = await analyzer._analyze_user_posts_with_llm(
            [mock_post], "tester"
        )

        assert len(items) == 1
        assert items[0].summary == "[분석 실패]"
        assert trend is None

    @patch("insight.tasks.weekly_user_trend_analysis.UserWeeklyAnalyzer._create_user_reminder")
    async def test_analyze_user_data_without_new_posts_creates_reminder(
        self, mock_reminder, analyzer, mock_context
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

        insight = await analyzer._analyze_user_data(user_data, mock_context)
        assert insight.user_weekly_reminder.title == "최근 글"
        mock_reminder.assert_called_once()

    @patch("insight.tasks.weekly_user_trend_analysis.UserWeeklyTrend.objects.create")
    async def test_save_results_success(
        self, mock_create, analyzer, mock_context
    ):
        """사용자 게시글 분석 결과 저장 성공 테스트"""
        mock_result = {
            "user_id": 1,
            "insight": MagicMock(to_dict=lambda: {"dummy": True}),
        }

        with patch.object(analyzer, "logger") as mock_logger:
            await analyzer._save_results([mock_result], mock_context)

            mock_create.assert_called_once()
            mock_logger.info.assert_called()

    @patch(
        "insight.tasks.weekly_user_trend_analysis.UserWeeklyTrend.objects.create",
        side_effect=[Exception("fail"), None],
    )
    async def test_save_results_continues_on_partial_failure(
        self, mock_create, analyzer, mock_context
    ):
        """분석 결과 중 일부 저장 실패가 발생해도 나머지 결과 저장이 계속 진행되는지 테스트"""
        result1 = {
            "user_id": 1,
            "insight": MagicMock(to_dict=lambda: {"dummy": True}),
        }
        result2 = {
            "user_id": 2,
            "insight": MagicMock(to_dict=lambda: {"dummy": True}),
        }

        with patch.object(analyzer, "logger") as mock_logger:
            await analyzer._save_results([result1, result2], mock_context)

            assert mock_create.call_count == 2
            mock_logger.error.assert_called_once()
            mock_logger.info.assert_called()
