from unittest.mock import MagicMock, patch

import pytest

from insight.models import UserWeeklyTrend, WeeklyTrend
from noti.models import NotiMailLog
from users.models import User
from utils.utils import get_local_now


@pytest.fixture
def mock_setup_django():
    """setup_django 모듈 모킹"""
    import sys
    from unittest.mock import MagicMock

    # setup_django 모듈을 sys.modules에 추가
    sys.modules["setup_django"] = MagicMock()
    return sys.modules["setup_django"]


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
    def test_delete_old_maillogs_success(self, newsletter_batch):
        """7일 이전 메일 로그 삭제 성공 테스트"""
        with patch.object(NotiMailLog.objects, "filter") as mock_filter:
            # Given
            mock_delete = MagicMock()
            mock_filter.return_value.delete = mock_delete
            mock_delete.return_value = (2, {"noti.NotiMailLog": 2})

            # When
            newsletter_batch._delete_old_maillogs()

            # Then
            mock_filter.assert_called_once_with(
                created_at__lt=newsletter_batch.before_a_week, is_success=True
            )
            mock_delete.assert_called_once()

    def test_get_target_user_chunks_success(self, newsletter_batch, user):
        """대상 유저 청크 조회 성공 테스트"""
        # Given
        mock_users = [
            {"id": user.id, "email": user.email, "username": user.username}
        ]

        with patch.object(User.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value.distinct.return_value = mock_users

            # When
            chunks = newsletter_batch._get_target_user_chunks()

            # Then
            assert len(chunks) == 1
            assert len(chunks[0]) == 1
            assert chunks[0][0]["email"] == user.email

    def test_get_weekly_trend_html_success(
        self, newsletter_batch, weekly_trend
    ):
        """주간 트렌드 HTML 생성 성공 테스트"""
        # Given
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
                    "<div>이 주의 트렌딩 글</div><div>트렌드 분석</div>"
                )

                # When
                newsletter_batch._get_weekly_trend_html()

                # Then
                mock_filter.assert_called_once_with(
                    week_end_date__gte=newsletter_batch.before_a_week,
                    is_processed=False,
                )
                assert (
                    newsletter_batch.weekly_info["newsletter_id"]
                    == weekly_trend.id
                )

    def test_get_weekly_trend_html_no_data_failure(self, newsletter_batch):
        """주간 트렌드 데이터 없음 실패 테스트"""
        # Given
        with patch.object(WeeklyTrend.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value.first.return_value = (
                None
            )

            # When & Then
            with pytest.raises(
                Exception, match="No WeeklyTrend data, batch stopped"
            ):
                newsletter_batch._get_weekly_trend_html()

    def test_get_users_weekly_trend_chunk_success(
        self, newsletter_batch, user_weekly_trend
    ):
        """유저 주간 트렌드 청크 조회 성공 테스트"""
        # Given
        user_ids = [user_weekly_trend.user.id]
        mock_trends = [
            {
                "user_id": user_weekly_trend.user.id,
                "insight": user_weekly_trend.insight,
            }
        ]

        with patch.object(UserWeeklyTrend.objects, "filter") as mock_filter:
            mock_filter.return_value.values.return_value = mock_trends

            # When
            trends = newsletter_batch._get_users_weekly_trend_chunk(user_ids)

            # Then
            mock_filter.assert_called_once_with(
                week_end_date__gte=newsletter_batch.before_a_week,
                user_id__in=user_ids,
                is_processed=False,
            )
            assert len(trends) == 1
            assert user_weekly_trend.user.id in trends

    def test_build_newsletters_success(self, newsletter_batch, user):
        """뉴스레터 객체 생성 성공 테스트"""
        # Given
        user_chunk = [
            {
                "id": user.id,
                "email": user.email,
                "username": user.username,
            }
        ]

        with patch.object(
            newsletter_batch, "_get_users_weekly_trend_chunk"
        ) as mock_get_trends:
            mock_get_trends.return_value = {
                user.id: MagicMock(user_stats={"total_views": 1000})
            }

            with patch.object(
                newsletter_batch, "_get_user_weekly_trend_html"
            ) as mock_get_html:
                mock_get_html.return_value = "<div>User Trend HTML</div>"

                with patch(
                    "insight.tasks.weekly_newsletter_batch.render_to_string"
                ) as mock_render:
                    mock_render.return_value = (
                        "<div>Final Newsletter HTML</div>"
                    )

                    # When
                    newsletters = newsletter_batch._build_newsletters(
                        user_chunk, "<div>Weekly Trend HTML</div>"
                    )

                    # Then
                    mock_get_trends.assert_called_once_with([user.id])
                    assert len(newsletters) == 1
                    assert newsletters[0].user_id == user.id
                    assert newsletters[0].email_message.to[0] == user.email

    def test_send_newsletters_success(
        self, newsletter_batch, sample_newsletters
    ):
        """뉴스레터 발송 성공 테스트"""
        # Given
        newsletter_batch.ses_client.send_email.return_value = None

        # When
        success_ids = newsletter_batch._send_newsletters(sample_newsletters)

        # Then
        assert len(success_ids) == 1
        assert success_ids[0] == sample_newsletters[0].user_id
        newsletter_batch.ses_client.send_email.assert_called_once()

    def test_send_newsletters_with_retry_success(
        self, newsletter_batch, sample_newsletters
    ):
        """뉴스레터 발송 재시도 성공 테스트"""
        # Given
        newsletter_batch.ses_client.send_email.side_effect = [
            Exception("First attempt failed"),
            None,
        ]

        # When
        success_ids = newsletter_batch._send_newsletters(sample_newsletters)

        # Then
        assert len(success_ids) == 1
        assert success_ids[0] == sample_newsletters[0].user_id
        assert newsletter_batch.ses_client.send_email.call_count == 2

    def test_update_weekly_trend_result_success(
        self, newsletter_batch, weekly_trend
    ):
        """주간 트렌드 결과 업데이트 성공 테스트"""
        # Given
        newsletter_batch.weekly_info = {
            "newsletter_id": weekly_trend.id,
            "s_date": weekly_trend.week_start_date,
            "e_date": weekly_trend.week_end_date,
        }

        with patch.object(WeeklyTrend.objects, "filter") as mock_filter:
            mock_update = MagicMock()
            mock_filter.return_value.update = mock_update

            # When
            newsletter_batch._update_weekly_trend_result()

            # Then
            mock_filter.assert_called_once_with(id=weekly_trend.id)
            mock_update.assert_called_once()

    def test_update_user_weekly_trend_results_success(
        self, newsletter_batch, user_weekly_trend
    ):
        """유저 주간 트렌드 결과 업데이트 성공 테스트"""
        # Given
        success_user_ids = [user_weekly_trend.user.id]

        with patch.object(UserWeeklyTrend.objects, "filter") as mock_filter:
            mock_update = MagicMock()
            mock_filter.return_value.update = mock_update

            with patch(
                "insight.tasks.weekly_newsletter_batch.transaction"
            ) as mock_transaction:
                mock_transaction.atomic.return_value.__enter__ = MagicMock()
                mock_transaction.atomic.return_value.__exit__ = MagicMock()

                # When
                newsletter_batch._update_user_weekly_trend_results(
                    success_user_ids
                )

                # Then
                mock_filter.assert_called_once_with(
                    user_id__in=success_user_ids,
                    week_end_date__gte=newsletter_batch.before_a_week,
                )
                mock_update.assert_called_once()

    @patch("insight.tasks.weekly_newsletter_batch.get_local_now")
    def test_run_success(self, mock_get_local_now, newsletter_batch, user):
        """배치 실행 성공 테스트"""
        # Given
        mock_get_local_now.return_value = get_local_now()

        with patch.object(newsletter_batch, "_delete_old_maillogs"):
            with patch.object(
                newsletter_batch, "_get_target_user_chunks"
            ) as mock_get_chunks:
                mock_get_chunks.return_value = [
                    [{"id": user.id, "email": user.email}]
                ]

                with patch.object(
                    newsletter_batch, "_get_weekly_trend_html"
                ) as mock_get_html:
                    mock_get_html.return_value = "<div>Weekly Trend HTML</div>"

                    with patch.object(
                        newsletter_batch, "_build_newsletters"
                    ) as mock_build:
                        mock_newsletter = MagicMock()
                        mock_newsletter.user_id = user.id
                        mock_build.return_value = [mock_newsletter]

                        with patch.object(
                            newsletter_batch, "_send_newsletters"
                        ) as mock_send:
                            mock_send.return_value = [user.id]

                            with patch.object(
                                newsletter_batch,
                                "_update_user_weekly_trend_results",
                            ):
                                with patch.object(
                                    newsletter_batch,
                                    "_update_weekly_trend_result",
                                ):
                                    # When
                                    newsletter_batch.run()

                                    # Then
                                    newsletter_batch._delete_old_maillogs.assert_called_once()
                                    mock_get_chunks.assert_called_once()
                                    newsletter_batch._get_weekly_trend_html.assert_called_once()
                                    newsletter_batch._build_newsletters.assert_called()
                                    mock_send.assert_called_once()
                                    newsletter_batch._update_user_weekly_trend_results.assert_called_once()
                                    newsletter_batch._update_weekly_trend_result.assert_called_once()

    def test_run_no_target_users_failure(self, newsletter_batch):
        """대상 유저 없음 실패 테스트"""
        # Given
        with patch.object(
            newsletter_batch, "_get_target_user_chunks"
        ) as mock_get_chunks:
            mock_get_chunks.return_value = []

            # When & Then
            with pytest.raises(
                Exception,
                match="No target users found for newsletter, batch stopped",
            ):
                newsletter_batch.run()

    def test_run_no_weekly_trend_data_failure(self, newsletter_batch, user):
        """주간 트렌드 데이터 없음 실패 테스트"""
        # Given
        with patch.object(
            newsletter_batch, "_get_target_user_chunks"
        ) as mock_get_chunks:
            mock_get_chunks.return_value = [
                [
                    {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                    }
                ]
            ]

            with patch.object(
                newsletter_batch, "_get_weekly_trend_html"
            ) as mock_get_html:
                mock_get_html.side_effect = Exception(
                    "No WeeklyTrend data, batch stopped"
                )

                # When & Then
                with pytest.raises(
                    Exception, match="No WeeklyTrend data, batch stopped"
                ):
                    newsletter_batch.run()

    def test_send_newsletters_max_retry_exceeded_failure(
        self, newsletter_batch, sample_newsletters
    ):
        """최대 재시도 횟수 초과 실패 테스트"""
        # Given
        newsletter_batch.ses_client.send_email.side_effect = [
            Exception("First attempt failed"),
            Exception("Second attempt failed"),
            Exception("Third attempt failed"),
        ]

        # When
        success_ids = newsletter_batch._send_newsletters(sample_newsletters)

        # Then
        assert len(success_ids) == 0
        assert newsletter_batch.ses_client.send_email.call_count == 3

    def test_run_low_success_rate_scenario_success(
        self, newsletter_batch, user
    ):
        """성공률 50% 미만시 WeeklyTrend 업데이트 테스트"""
        # Given
        with patch.object(newsletter_batch, "_delete_old_maillogs"):
            with patch.object(
                newsletter_batch, "_get_target_user_chunks"
            ) as mock_get_chunks:
                mock_get_chunks.return_value = [
                    [{"id": user.id, "email": user.email}]
                ]

                with patch.object(
                    newsletter_batch, "_get_weekly_trend_html"
                ) as mock_get_html:
                    mock_get_html.return_value = "<div>Weekly Trend HTML</div>"

                    with patch.object(
                        newsletter_batch, "_build_newsletters"
                    ) as mock_build:
                        mock_newsletter = MagicMock()
                        mock_newsletter.user_id = user.id
                        mock_build.return_value = [mock_newsletter]

                        with patch.object(
                            newsletter_batch, "_send_newsletters"
                        ) as mock_send:
                            mock_send.return_value = []

                            with patch.object(
                                newsletter_batch,
                                "_update_user_weekly_trend_results",
                            ):
                                with patch.object(
                                    newsletter_batch,
                                    "_update_weekly_trend_result",
                                ) as mock_update:
                                    # When
                                    newsletter_batch.run()

                                    # Then
                                    mock_update.assert_not_called()

    def test_get_weekly_trend_html_invalid_template_failure(
        self, newsletter_batch, weekly_trend
    ):
        """템플릿 렌더링 실패 테스트"""
        # Given
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
                mock_render.return_value = "<div>Invalid Template</div>"

                # When & Then
                with pytest.raises(
                    Exception, match="Failed to build weekly trend HTML"
                ):
                    newsletter_batch._get_weekly_trend_html()

    def test_send_newsletters_mail_log_creation_failure_success(
        self, newsletter_batch, sample_newsletters
    ):
        """메일 로그 생성 실패 시에도 배치 진행 테스트"""
        # Given
        newsletter_batch.ses_client.send_email.return_value = None

        with patch.object(
            NotiMailLog.objects, "bulk_create"
        ) as mock_bulk_create:
            mock_bulk_create.side_effect = Exception("DB Error")

            # When
            success_ids = newsletter_batch._send_newsletters(
                sample_newsletters
            )

            # Then
            assert len(success_ids) == 1
            assert success_ids[0] == sample_newsletters[0].user_id
            newsletter_batch.ses_client.send_email.assert_called_once()
