from unittest.mock import patch

import pytest


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyUserTrendFetch:
    async def test_check_user_token_validity_success(
        self, analyzer_user, mock_context
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

            is_valid = await analyzer_user._check_user_token_validity(
                1, mock_context
            )
            assert is_valid is True

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    async def test_check_user_token_validity_with_no_posts(
        self, mock_posts, analyzer_user, mock_context
    ):
        """게시글이 없는 경우에도 토큰을 유효하다고 판단하는지 테스트"""
        mock_posts.filter.return_value.values_list.return_value = []

        is_valid = await analyzer_user._check_user_token_validity(
            1, mock_context
        )
        assert is_valid is True

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch(
        "insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects"
    )
    async def test_check_user_token_validity_failure(
        self, mock_stats, mock_posts, analyzer_user, mock_context
    ):
        """게시글은 있으나 통계가 없을 경우, 사용자 토큰을 무효하다고 판단하는지 테스트"""
        mock_posts.filter.return_value.values_list.return_value = [1]
        mock_stats.filter.return_value.count.return_value = 0

        with patch.object(analyzer_user, "logger") as mock_logger:
            is_valid = await analyzer_user._check_user_token_validity(
                1, mock_context
            )
            assert is_valid is False
            mock_logger.warning.assert_called_once()

    @patch("insight.tasks.weekly_user_trend_analysis.Post.objects")
    @patch(
        "insight.tasks.weekly_user_trend_analysis.PostDailyStatistics.objects"
    )
    async def test_collect_user_data_marks_token_expired_user(
        self, mock_stats, mock_posts, analyzer_user, mock_context
    ):
        """오늘자 통계가 없는 사용자는 본문을 조회하지 않고 expired_token_users에 추가하는지 테스트"""
        mock_posts.filter.return_value.values_list.return_value = [123]
        mock_stats.filter.return_value.count.return_value = 0

        with patch.object(analyzer_user, "logger") as mock_logger:
            user_data = await analyzer_user._collect_user_data(
                1, "tester", mock_context
            )

            assert user_data is None
            assert 1 in analyzer_user.expired_token_users
            assert 1 not in analyzer_user.successful_users
            mock_context.velog_client.get_post.assert_not_called()
            mock_logger.warning.assert_any_call(
                "User %s token expired - no today stats", 1
            )
