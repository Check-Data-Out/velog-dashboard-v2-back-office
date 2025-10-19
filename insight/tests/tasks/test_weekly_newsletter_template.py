from unittest.mock import MagicMock, patch

import pytest

from insight.models import WeeklyTrend, WeeklyUserTrendInsight
from utils.utils import from_dict


@pytest.fixture
def mock_ses_client():
    """SES 클라이언트 모킹"""
    from modules.mail.ses.client import SESClient

    mock_client = MagicMock(spec=SESClient)
    return mock_client


@pytest.fixture
def newsletter_batch(mock_setup_django, mock_ses_client):
    """WeeklyNewsletterBatch 인스턴스 생성"""
    from insight.tasks.weekly_newsletter_batch import WeeklyNewsletterBatch

    return WeeklyNewsletterBatch(
        ses_client=mock_ses_client,
        chunk_size=100,
        max_retry_count=3,
    )


class TestWeeklyNewsletterTemplate:
    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_get_weekly_trend_html_success(
        self, mock_logger, newsletter_batch, weekly_trend
    ):
        """주간 트렌드 HTML 생성 성공 테스트"""
        with patch.object(WeeklyTrend.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value.first.return_value = {
                "id": weekly_trend.id,
                "insight": weekly_trend.insight,
                "week_start_date": weekly_trend.week_start_date,
                "week_end_date": weekly_trend.week_end_date,
            }

            weekly_trend_html = newsletter_batch._get_weekly_trend_html()

            # 로직 검증
            mock_filter.assert_called_once_with(
                week_end_date__gte=newsletter_batch.before_a_week,
                is_processed=False,
            )
            assert (
                newsletter_batch.weekly_info["newsletter_id"]
                == weekly_trend.id
            )

            # 템플릿 렌더링 검증
            insight_data = weekly_trend.insight
            trending_summary = insight_data.get("trending_summary")
            trend_analysis = insight_data.get("trend_analysis")

            assert trending_summary[0]["title"] in weekly_trend_html
            assert trend_analysis["insights"] in weekly_trend_html
            assert "벨로그 주간 트렌드" in weekly_trend_html
            assert "이번 주의 트렌딩 글" in weekly_trend_html
            assert "주간 트렌드 분석" in weekly_trend_html

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_get_weekly_trend_html_no_data_failure(
        self, mock_logger, newsletter_batch
    ):
        """주간 트렌드 데이터 없음 실패 테스트"""
        with patch.object(WeeklyTrend.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value.first.return_value = (
                None
            )

            with pytest.raises(
                Exception, match="No WeeklyTrend data, batch stopped"
            ):
                newsletter_batch._get_weekly_trend_html()

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_get_weekly_trend_html_template_rendering_failure(
        self, mock_logger, newsletter_batch, weekly_trend
    ):
        """템플릿 렌더링 실패 시 예외 처리 테스트"""
        with patch.object(WeeklyTrend.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value.first.return_value = {
                "id": weekly_trend.id,
                "insight": weekly_trend.insight,
                "week_start_date": weekly_trend.week_start_date,
                "week_end_date": weekly_trend.week_end_date,
            }

            with patch(
                "insight.tasks.weekly_newsletter_batch.render_to_string"
            ) as mock_render:
                mock_render.return_value = (
                    "Invalid template without required elements"
                )

                with pytest.raises(
                    Exception, match="Failed to build weekly trend HTML"
                ):
                    newsletter_batch._get_weekly_trend_html()

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_get_user_weekly_trend_html_success(
        self, mock_logger, newsletter_batch, user, user_weekly_trend
    ):
        """주간 글 작성 사용자 주간 트렌드 HTML 렌더링 테스트"""
        user_weekly_trend_html = newsletter_batch._get_user_weekly_trend_html(
            {"id": user.id, "username": user.username, "email": user.email},
            from_dict(WeeklyUserTrendInsight, user_weekly_trend.insight),
        )

        # 템플릿 렌더링 검증
        insight_data = user_weekly_trend.insight
        trending_summary = insight_data.get("trending_summary")
        trend_analysis = insight_data.get("trend_analysis")
        user_weekly_stats = insight_data.get("user_weekly_stats")

        assert trending_summary[0]["title"] in user_weekly_trend_html
        assert trend_analysis["insights"] in user_weekly_trend_html
        assert (
            f'{user_weekly_stats["new_posts"]}개의 글'
            in user_weekly_trend_html
        )
        assert "마지막으로 글을 작성하신지" not in user_weekly_trend_html
        assert user.username in user_weekly_trend_html
        assert "이번주에 작성한 글" in user_weekly_trend_html
        assert "주간 내 활동 분석" in user_weekly_trend_html

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_get_user_weekly_trend_html_inactive_user(
        self, mock_logger, newsletter_batch, user, inactive_user_weekly_trend
    ):
        """주간 글 미작성 사용자 주간 트렌드 HTML 렌더링 테스트"""
        user_weekly_trend_html = newsletter_batch._get_user_weekly_trend_html(
            {"id": user.id, "username": user.username, "email": user.email},
            from_dict(
                WeeklyUserTrendInsight, inactive_user_weekly_trend.insight
            ),
        )

        # 템플릿 렌더링 검증
        insight_data = inactive_user_weekly_trend.insight
        user_weekly_reminder = insight_data.get("user_weekly_reminder")

        assert "이번주에 작성한 글" not in user_weekly_trend_html
        assert "주간 내 활동 분석" not in user_weekly_trend_html
        # days_ago가 있는 경우와 없는 경우 모두 처리
        if user_weekly_reminder.get("days_ago"):
            assert (
                f'😭 마지막으로 글을 작성하신지 {user_weekly_reminder["days_ago"]}일이 지났어요!'
                in user_weekly_trend_html
            )
        else:
            assert "😭 글을 작성하지 않으셨네요!" in user_weekly_trend_html

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_get_user_weekly_trend_html_exception(
        self, mock_logger, newsletter_batch, user
    ):
        """주간 트렌드 템플릿 렌더링 실패 테스트"""
        with patch(
            "insight.tasks.weekly_newsletter_batch.render_to_string"
        ) as mock_render:
            mock_render.side_effect = Exception("Template rendering failed")

            with pytest.raises(Exception):
                newsletter_batch._get_user_weekly_trend_html(
                    {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                    },
                    None,
                )

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_get_newsletter_html_success(
        self, mock_logger, newsletter_batch, user
    ):
        """정상 사용자 뉴스레터 HTML 렌더링 테스트"""
        is_expired_token_user = False
        weekly_trend_html = "test-weekly-trend-html"
        user_weekly_trend_html = "test-user-weekly-trend-html"

        newsletter_html = newsletter_batch._get_newsletter_html(
            user,
            is_expired_token_user,
            weekly_trend_html,
            user_weekly_trend_html,
        )

        # 템플릿 렌더링 검증
        assert "토큰이 만료" not in newsletter_html
        assert weekly_trend_html in newsletter_html
        assert user_weekly_trend_html in newsletter_html
        assert "대시보드 보러가기" in newsletter_html
        assert "Weekly Report" in newsletter_html
        assert "Velog Dashboard" in newsletter_html
        assert (
            "user/newsletter-unsubscribe?email=" + user.email
            in newsletter_html
        )

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_get_newsletter_html_expired_token_user(
        self, mock_logger, newsletter_batch, user
    ):
        """토큰 만료 사용자 뉴스레터 HTML 렌더링 테스트"""
        is_expired_token_user = True
        weekly_trend_html = "test-weekly-trend-html"
        user_weekly_trend_html = "test-user-weekly-trend-html"

        newsletter_html = newsletter_batch._get_newsletter_html(
            user,
            is_expired_token_user,
            weekly_trend_html,
            user_weekly_trend_html,
        )

        # 템플릿 렌더링 검증
        assert "🚨 잠시만요, 토큰이 만료된 것 같아요!" in newsletter_html
        assert (
            "토큰이 만료되어 정상적으로 통계를 수집할 수 없었어요"
            in newsletter_html
        )
        assert weekly_trend_html in newsletter_html
        assert user_weekly_trend_html not in newsletter_html
        assert "대시보드 보러가기" in newsletter_html
        assert "활동 리포트" in newsletter_html
        assert (
            "user/newsletter-unsubscribe?email=" + user.email
            in newsletter_html
        )

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_get_newsletter_html_exception(
        self, mock_logger, newsletter_batch, user
    ):
        """뉴스레터 HTML 렌더링 실패 시 예외 처리 테스트"""
        with patch(
            "insight.tasks.weekly_newsletter_batch.render_to_string"
        ) as mock_render:
            mock_render.side_effect = Exception("Template rendering failed")

            with pytest.raises(Exception):
                newsletter_batch._get_newsletter_html(
                    user,
                    False,
                    "test-weekly-trend-html",
                    "test-user-weekly-trend-html",
                )
