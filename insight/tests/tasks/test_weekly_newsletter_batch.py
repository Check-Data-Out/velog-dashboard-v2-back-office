from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from insight.models import UserWeeklyTrend, WeeklyTrend
from noti.models import NotiMailLog
from users.models import User
from utils.utils import get_local_now


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


class TestWeeklyNewsletterBatch:
    """뉴스레터 배치 테스트"""

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_delete_old_maillogs_success(self, mock_logger, newsletter_batch):
        """이전 뉴스레터 성공 메일 로그 삭제 성공 테스트"""
        with patch.object(NotiMailLog.objects, "filter") as mock_filter:
            mock_delete = MagicMock()
            mock_filter.return_value.delete = mock_delete
            mock_delete.return_value = (2, {"noti.NotiMailLog": 2})

            newsletter_batch._delete_old_maillogs()

            mock_filter.assert_called_once_with(
                sent_at__lt=newsletter_batch.before_a_week + timedelta(days=1),
                is_success=True,
            )
            mock_delete.assert_called_once()

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_delete_old_maillogs_integration(
        self, mock_logger, newsletter_batch, user
    ):
        """이전 뉴스레터 성공 메일 로그 삭제 테스트"""
        # 오래된 성공 메일 로그 (삭제 대상)
        old_success_log = NotiMailLog.objects.create(
            user=user,
            subject="Weekly Newsletter #1",
            body="old success newsletter",
            is_success=True,
        )

        # 오래된 실패 메일 로그 (삭제되지 않음)
        old_fail_log = NotiMailLog.objects.create(
            user=user,
            subject="Weekly Newsletter #1",
            body="old fail newsletter",
            is_success=False,
        )

        # 과거 데이터로 설정
        before_a_week = get_local_now() - timedelta(weeks=1)
        old_success_log.sent_at = before_a_week
        old_fail_log.sent_at = before_a_week
        NotiMailLog.objects.bulk_update(
            [old_success_log, old_fail_log], ["sent_at"]
        )

        # 현재 성공한 메일 로그 (삭제되지 않음)
        new_log = NotiMailLog.objects.create(
            user=user,
            subject="Weekly Newsletter #2",
            body="new success newsletter",
            is_success=True,
        )

        newsletter_batch._delete_old_maillogs()

        # 삭제 후 상태 확인
        remaining_logs_id = [
            log["id"] for log in NotiMailLog.objects.all().values("id")
        ]

        assert old_success_log.id not in remaining_logs_id
        assert old_fail_log.id in remaining_logs_id
        assert new_log.id in remaining_logs_id
        assert len(remaining_logs_id) == 2

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_get_target_user_chunks_success(
        self, mock_logger, newsletter_batch, user
    ):
        """대상 유저 청크 조회 성공 테스트"""
        mock_users = [
            {"id": user.id, "email": user.email, "username": user.username}
        ]

        with patch.object(User.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value.distinct.return_value = mock_users

            chunks = newsletter_batch._get_target_user_chunks()

            assert len(chunks) == 1
            assert len(chunks[0]) == 1
            assert chunks[0][0]["email"] == user.email

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_get_target_user_chunks_failure(
        self, mock_logger, newsletter_batch
    ):
        """대상 유저 청크 조회 실패 테스트"""
        with patch.object(User.objects, "filter") as mock_filter:
            mock_filter.side_effect = Exception("DB Error")

            with pytest.raises(Exception, match="DB Error"):
                newsletter_batch._get_target_user_chunks()

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_get_users_weekly_trend_chunk_success(
        self, mock_logger, newsletter_batch, user_weekly_trend
    ):
        """유저 주간 트렌드 청크 조회 성공 테스트"""
        user_ids = [user_weekly_trend.user.id]
        mock_trends = [
            {
                "user_id": user_weekly_trend.user.id,
                "insight": user_weekly_trend.insight,
            }
        ]

        with patch.object(UserWeeklyTrend.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value = mock_trends

            trends = newsletter_batch._get_users_weekly_trend_chunk(user_ids)

            mock_filter.assert_called_once_with(
                week_end_date__gte=newsletter_batch.before_a_week,
                user_id__in=user_ids,
                is_processed=False,
            )
            assert len(trends) == 1
            assert user_weekly_trend.user.id in trends

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_build_newsletters_success(
        self, mock_logger, newsletter_batch, user
    ):
        """뉴스레터 객체 생성 성공 테스트"""
        user_chunk = [
            {
                "id": user.id,
                "email": user.email,
                "username": user.username,
            }
        ]

        with (
            patch.object(
                newsletter_batch, "_get_users_weekly_trend_chunk"
            ) as mock_get_trends,
            patch.object(
                newsletter_batch, "_get_user_weekly_trend_html"
            ) as mock_get_html,
            patch(
                "insight.tasks.weekly_newsletter_batch.render_to_string"
            ) as mock_render,
        ):
            mock_get_trends.return_value = {
                user.id: MagicMock(user_stats={"total_views": 1000})
            }
            mock_get_html.return_value = "<div>User Trend HTML</div>"
            mock_render.return_value = "<div>Final Newsletter HTML</div>"

            newsletters = newsletter_batch._build_newsletters(
                user_chunk, "<div>Weekly Trend HTML</div>"
            )

            mock_get_trends.assert_called_once_with([user.id])
            assert len(newsletters) == 1
            assert newsletters[0].user_id == user.id
            assert newsletters[0].email_message.to[0] == user.email

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_send_newsletters_success(
        self, mock_logger, newsletter_batch, sample_newsletters
    ):
        """뉴스레터 발송 성공 테스트 (재시도 포함)"""
        newsletter_batch.ses_client.send_email.side_effect = [
            Exception("First attempt failed"),
            None,  # 두 번째 시도 성공
        ]

        success_ids = newsletter_batch._send_newsletters(sample_newsletters)

        assert len(success_ids) == 1
        assert success_ids[0] == sample_newsletters[0].user_id
        assert newsletter_batch.ses_client.send_email.call_count == 2

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_send_newsletters_max_retry_exceeded_failure(
        self, mock_logger, newsletter_batch, sample_newsletters
    ):
        """최대 재시도 횟수 초과 실패 테스트"""
        newsletter_batch.ses_client.send_email.side_effect = [
            Exception("First attempt failed"),
            Exception("Second attempt failed"),
            Exception("Third attempt failed"),
        ]

        success_ids = newsletter_batch._send_newsletters(sample_newsletters)

        assert len(success_ids) == 0
        assert newsletter_batch.ses_client.send_email.call_count == 3

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_update_weekly_trend_result_success(
        self, mock_logger, newsletter_batch, weekly_trend
    ):
        """주간 트렌드 결과 업데이트 성공 테스트"""
        newsletter_batch.weekly_info = {
            "newsletter_id": weekly_trend.id,
            "s_date": weekly_trend.week_start_date,
            "e_date": weekly_trend.week_end_date,
        }

        with patch.object(WeeklyTrend.objects, "filter") as mock_filter:
            mock_update = MagicMock()
            mock_filter.return_value.update = mock_update

            newsletter_batch._update_weekly_trend_result()

            mock_filter.assert_called_once_with(id=weekly_trend.id)
            mock_update.assert_called_once()

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_update_user_weekly_trend_results_success(
        self, mock_logger, newsletter_batch, user_weekly_trend
    ):
        """유저 주간 트렌드 결과 업데이트 성공 테스트"""
        success_user_ids = [user_weekly_trend.user.id]

        with (
            patch.object(UserWeeklyTrend.objects, "filter") as mock_filter,
            patch(
                "insight.tasks.weekly_newsletter_batch.transaction"
            ) as mock_transaction,
        ):
            mock_update = MagicMock()
            mock_filter.return_value.update = mock_update
            mock_transaction.atomic.return_value.__enter__ = MagicMock()
            mock_transaction.atomic.return_value.__exit__ = MagicMock()

            newsletter_batch._update_user_weekly_trend_results(
                success_user_ids
            )

            mock_filter.assert_called_once_with(
                user_id__in=success_user_ids,
                week_end_date__gte=newsletter_batch.before_a_week,
            )
            mock_update.assert_called_once()

    @patch("insight.tasks.weekly_newsletter_batch.get_local_now")
    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_run_success(
        self, mock_logger, mock_get_local_now, newsletter_batch, user
    ):
        """배치 실행 성공 테스트"""
        mock_get_local_now.return_value = get_local_now()

        with (
            patch.object(
                newsletter_batch, "_delete_old_maillogs"
            ) as mock_delete,
            patch.object(
                newsletter_batch, "_get_target_user_chunks"
            ) as mock_get_chunks,
            patch.object(
                newsletter_batch, "_get_weekly_trend_html"
            ) as mock_get_html,
            patch.object(newsletter_batch, "_build_newsletters") as mock_build,
            patch.object(newsletter_batch, "_send_newsletters") as mock_send,
            patch.object(
                newsletter_batch, "_update_user_weekly_trend_results"
            ) as mock_update_user,
            patch.object(
                newsletter_batch, "_update_weekly_trend_result"
            ) as mock_update_weekly,
        ):
            mock_get_chunks.return_value = [
                [{"id": user.id, "email": user.email}]
            ]
            mock_get_html.return_value = "<div>Weekly Trend HTML</div>"

            mock_newsletter = MagicMock()
            mock_newsletter.user_id = user.id
            mock_build.return_value = [mock_newsletter]
            mock_send.return_value = [user.id]

            newsletter_batch.run()

            mock_delete.assert_called_once()
            mock_get_chunks.assert_called_once()
            mock_get_html.assert_called_once()
            mock_build.assert_called_once()
            mock_send.assert_called_once()
            mock_update_user.assert_called_once()
            mock_update_weekly.assert_called_once()

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_run_no_target_users_failure(self, mock_logger, newsletter_batch):
        """대상 유저 없음 실패 테스트"""
        with patch.object(
            newsletter_batch, "_get_target_user_chunks"
        ) as mock_get_chunks:
            mock_get_chunks.return_value = []

            with pytest.raises(
                Exception,
                match="No target users found for newsletter, batch stopped",
            ):
                newsletter_batch.run()

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_run_no_weekly_trend_data_failure(
        self, mock_logger, newsletter_batch, user
    ):
        """주간 트렌드 데이터 없음 실패 테스트"""
        with (
            patch.object(
                newsletter_batch, "_get_target_user_chunks"
            ) as mock_get_chunks,
            patch.object(
                newsletter_batch, "_get_weekly_trend_html"
            ) as mock_get_html,
        ):
            mock_get_chunks.return_value = [
                [
                    {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                    }
                ]
            ]
            mock_get_html.side_effect = Exception(
                "No WeeklyTrend data, batch stopped"
            )

            with pytest.raises(
                Exception, match="No WeeklyTrend data, batch stopped"
            ):
                newsletter_batch.run()
