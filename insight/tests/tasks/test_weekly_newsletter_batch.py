from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.db import DatabaseError

from insight.models import (
    BATCH_NEWSLETTER_STARTED,
    BATCH_STATE_KEY,
    BATCH_USER_ANALYSIS_COMPLETED,
    WeeklyTrend,
)
from modules.mail.exceptions import AuthenticationError, SendingBlockedError
from modules.mail.unsubscribe import (
    build_legacy_unsubscribe_url,
    build_unsubscribe_url,
)
from noti.models import NotiMailLog
from users.models import User
from utils.utils import get_local_now, get_this_week_monday

SKIP_MARKER = "weekly_newsletter_batch.skipped"
RESULT_FILE = "newsletter_batch_result.txt"


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
                # 느슨한 시간 적용
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
            mock_filter.return_value.exclude.return_value.values.return_value.distinct.return_value = mock_users

            chunks = newsletter_batch._get_target_user_chunks()

            mock_filter.assert_called_once_with(
                is_active=True,
                email__isnull=False,
                newsletter_subscribed=True,
            )
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
    @pytest.mark.usefixtures("monday")
    def test_get_users_weekly_trend_chunk_success(
        self, mock_logger, newsletter_batch, user_weekly_trend
    ):
        """유저 주간 트렌드 청크 조회 성공 테스트"""
        user_ids = [user_weekly_trend.user.id]

        trends = newsletter_batch._get_users_weekly_trend_chunk(user_ids)

        assert list(trends) == user_ids

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
            # 제목 포맷 검증
            assert (
                "벨로그 대시보드 주간 뉴스레터"
                in newsletters[0].email_message.subject
            )

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_build_newsletters_sets_one_click_unsubscribe_headers(
        self,
        mock_logger,
        newsletter_batch,
        user,
        newsletter_unsubscribe_secret,
    ):
        """사용자별 서명 수신거부 URL 을 원클릭 수신거부 헤더에 넣는다"""
        user_chunk = [
            {"id": user.id, "email": user.email, "username": user.username}
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
            mock_get_trends.return_value = {user.id: MagicMock()}
            mock_get_html.return_value = "<div>User Trend HTML</div>"
            mock_render.return_value = "<div>Final Newsletter HTML</div>"

            newsletters = newsletter_batch._build_newsletters(
                user_chunk, "<div>Weekly Trend HTML</div>"
            )

        unsubscribe_url = build_unsubscribe_url(
            newsletter_unsubscribe_secret, user.id
        )
        assert newsletters[0].email_message.headers == [
            ("List-Unsubscribe", f"<{unsubscribe_url}>"),
            ("List-Unsubscribe-Post", "List-Unsubscribe=One-Click"),
        ]
        # 본문 링크도 헤더와 같은 서명 URL 을 쓴다
        assert (
            mock_render.call_args.args[1]["unsubscribe_url"] == unsubscribe_url
        )

    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
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
    @pytest.mark.django_db
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
        # 실패 로그는 공개 Actions 로그에 남으므로 수신자 주소 대신 user id 만 담는다
        logged = str(mock_logger.mock_calls)
        assert sample_newsletters[0].email_message.to[0] not in logged
        assert f"(id: {sample_newsletters[0].user_id})" in logged

    @pytest.mark.parametrize(
        "error_cls", [AuthenticationError, SendingBlockedError]
    )
    @patch("insight.tasks.weekly_newsletter_batch.logger")
    @pytest.mark.django_db
    def test_send_newsletters_stops_when_sending_is_blocked(
        self,
        mock_logger,
        error_cls,
        newsletter_batch,
        sample_newsletter,
    ):
        """인증 실패·계정 발송 정지는 재시도·남은 발송 없이 결과를 남기고 배치를 멈춘다"""
        newsletter_batch.ses_client.send_email.side_effect = error_cls(
            "blocked"
        )
        newsletter_batch._update_user_weekly_trend_results = MagicMock()

        with pytest.raises(error_cls, match="blocked"):
            newsletter_batch._send_newsletters(
                [sample_newsletter, sample_newsletter]
            )

        assert newsletter_batch.ses_client.send_email.call_count == 1
        newsletter_batch._update_user_weekly_trend_results.assert_called_once_with(
            []
        )
        # 멈춘 메일의 실패 기록은 남긴다
        assert list(
            NotiMailLog.objects.values_list("is_success", "error_message")
        ) == [(False, "blocked")]

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
    @pytest.mark.usefixtures("monday")
    def test_update_user_weekly_trend_results_success(
        self, mock_logger, newsletter_batch, user_weekly_trend
    ):
        """유저 주간 트렌드 결과 업데이트 성공 테스트"""
        newsletter_batch._update_user_weekly_trend_results(
            [user_weekly_trend.user.id]
        )

        user_weekly_trend.refresh_from_db()
        assert user_weekly_trend.is_processed is True

    @pytest.mark.parametrize(
        "secret",
        ["", "x" * 31],
        ids=["empty", "shorter_than_32_bytes"],
    )
    @patch("insight.tasks.weekly_newsletter_batch.render_to_string")
    @patch("insight.tasks.weekly_newsletter_batch.logger")
    def test_build_newsletters_without_usable_secret_uses_legacy_email_link(
        self,
        mock_logger,
        mock_render,
        newsletter_batch,
        user,
        settings,
        secret,
    ):
        """서명 키가 비었거나 32바이트보다 짧아도 발송을 멈추지 않고 기존 email 링크로 보내며 원클릭 헤더는 붙이지 않는다"""
        settings.NEWSLETTER_UNSUBSCRIBE_SECRET = secret
        mock_render.return_value = "<div>Final Newsletter HTML</div>"
        user_chunk = [
            {"id": user.id, "email": user.email, "username": user.username}
        ]

        with (
            patch.object(
                newsletter_batch,
                "_get_users_weekly_trend_chunk",
                return_value={user.id: MagicMock()},
            ),
            patch.object(
                newsletter_batch,
                "_get_user_weekly_trend_html",
                return_value="<div>User Trend HTML</div>",
            ),
        ):
            newsletters = newsletter_batch._build_newsletters(
                user_chunk, "<div>Weekly Trend HTML</div>"
            )

        assert newsletters[0].email_message.headers is None
        assert mock_render.call_args.args[1][
            "unsubscribe_url"
        ] == build_legacy_unsubscribe_url(user.email)

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


def create_this_week_trend(
    insight: dict, completed: bool = True, **fields
) -> WeeklyTrend:
    """이번 주 공통 분석 행(종료일이 지난 일요일). completed 면 사용자 분석 완료 표시를 담는다"""
    week_end = get_this_week_monday() - timedelta(days=1)
    if completed:
        insight[BATCH_STATE_KEY] = {
            BATCH_USER_ANALYSIS_COMPLETED: get_local_now().isoformat()
        }
    return WeeklyTrend.objects.create(
        week_start_date=week_end - timedelta(days=6),
        week_end_date=week_end,
        insight=insight,
        **fields,
    )


class ProcessKilled(BaseException):
    """어디서도 잡지 않는 예외. 발송 도중 프로세스가 죽는 상황을 흉내 낸다"""


def create_old_mail_log(user: User, sent_at: datetime) -> NotiMailLog:
    """sent_at 에 성공한 발송 기록. 지난 기록 삭제가 돌면 지워진다"""
    log = NotiMailLog.objects.create(
        user=user, subject="벨로그 대시보드 주간 뉴스레터 #0", is_success=True
    )
    # sent_at 은 auto_now_add 라서 만든 뒤에 바꾼다
    NotiMailLog.objects.filter(pk=log.pk).update(sent_at=sent_at)
    return log


@pytest.mark.django_db
@pytest.mark.usefixtures("monday")
class TestWeeklyNewsletterBatchRun:
    """실제 DB·템플릿으로 run() 전체를 돌리는 테스트. 오늘은 월요일로 고정한다"""

    def test_sends_to_every_target_and_marks_week_processed(
        self,
        newsletter_batch,
        work_dir,
        user,
        create_user,
        sample_weekly_trend_insight,
    ):
        """대상 이메일마다 메일을 한 통씩 보내고 이번 주 행을 발송 완료로 표시한다"""
        create_user("other@example.com")
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict()
        )

        newsletter_batch.run()

        assert newsletter_batch.ses_client.send_email.call_count == 2
        trend.refresh_from_db()
        assert trend.is_processed is True
        # Slack 에 그대로 옮겨지므로 결과는 실제 줄바꿈으로 나뉜 줄이다
        assert (work_dir / RESULT_FILE).read_text().splitlines()[0] == (
            "✅ 뉴스레터 발송 완료: 성공 2명, 실패 0명"
        )

    def test_skips_before_deleting_logs_when_this_week_is_sent(
        self,
        newsletter_batch,
        work_dir,
        user,
        monday,
        sample_weekly_trend_insight,
    ):
        """이번 주 뉴스레터를 이미 보냈으면 지난 발송 기록을 지우지 않고 메일 없이 건너뜀 표시를 남긴다"""
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict(), is_processed=True
        )
        NotiMailLog.objects.create(
            user=user,
            subject=f"벨로그 대시보드 주간 뉴스레터 #{trend.id}",
            is_success=True,
        )
        old_log = create_old_mail_log(user, monday - timedelta(weeks=2))

        newsletter_batch.run()

        assert NotiMailLog.objects.filter(pk=old_log.pk).exists()
        newsletter_batch.ses_client.send_email.assert_not_called()
        assert (work_dir / SKIP_MARKER).exists()
        assert "건너뜀" in (work_dir / RESULT_FILE).read_text()

    def test_reports_processed_week_without_mail_log(
        self, newsletter_batch, work_dir, user, sample_weekly_trend_insight
    ):
        """처리 완료 표시만 있고 이번 주 발송 기록이 없으면 메일을 보내지 않고, 건너뜀 표시 없이 성공으로 끝나 Slack 이 가게 한다"""
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict(), is_processed=True
        )
        # 실패 기록과 다른 주의 성공 기록은 이번 주 발송 기록이 아니다
        NotiMailLog.objects.create(
            user=user,
            subject=f"벨로그 대시보드 주간 뉴스레터 #{trend.id}",
            is_success=False,
        )
        NotiMailLog.objects.create(
            user=user,
            subject=f"벨로그 대시보드 주간 뉴스레터 #{trend.id + 1}",
            is_success=True,
        )

        newsletter_batch.run()

        newsletter_batch.ses_client.send_email.assert_not_called()
        assert not (work_dir / SKIP_MARKER).exists()
        assert (
            "처리 완료 표시는 있으나 이번 주 발송 기록이 없음"
            in (work_dir / RESULT_FILE).read_text()
        )

    def test_fails_without_mail_when_user_analysis_is_not_completed(
        self,
        newsletter_batch,
        work_dir,
        user,
        monday,
        sample_weekly_trend_insight,
    ):
        """사용자 분석 완료 표시가 없으면 기록을 지우지 않고 메일 0통으로 실패한다"""
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict(), completed=False
        )
        old_log = create_old_mail_log(user, monday - timedelta(weeks=2))

        with pytest.raises(Exception, match="analysis is not completed"):
            newsletter_batch.run()

        assert NotiMailLog.objects.filter(pk=old_log.pk).exists()
        newsletter_batch.ses_client.send_email.assert_not_called()
        trend.refresh_from_db()
        assert trend.batch_value(BATCH_NEWSLETTER_STARTED) is None
        assert trend.is_processed is False

    def test_skips_emails_that_already_received_this_newsletter(
        self,
        newsletter_batch,
        work_dir,
        user,
        create_user,
        sample_weekly_trend_insight,
    ):
        """이번 주 뉴스레터를 이미 받은 이메일은 다른 계정으로도 다시 받지 않는다"""
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict()
        )
        subject = f"벨로그 대시보드 주간 뉴스레터 #{trend.id}"
        # user 는 이미 받았고, 같은 이메일의 다른 계정은 받은 기록이 없다
        NotiMailLog.objects.create(user=user, subject=subject, is_success=True)
        create_user(user.email)
        # 실패 기록만 있는 이메일은 다시 받는다
        failed = create_user("failed@example.com")
        NotiMailLog.objects.create(
            user=failed, subject=subject, is_success=False
        )
        # 다른 주 뉴스레터를 받은 이메일은 이번 주 것을 받는다
        other_week = create_user("other-week@example.com")
        NotiMailLog.objects.create(
            user=other_week,
            subject=f"벨로그 대시보드 주간 뉴스레터 #{trend.id + 1}",
            is_success=True,
        )
        # 계정이 지워져 수신자가 빈 성공 기록은 누구도 빼지 않는다
        NotiMailLog.objects.create(user=None, subject=subject, is_success=True)

        newsletter_batch.run()

        recipients = sorted(
            call.args[0].to[0]
            for call in newsletter_batch.ses_client.send_email.call_args_list
        )
        assert recipients == ["failed@example.com", "other-week@example.com"]

    def test_marks_week_processed_when_every_target_already_received(
        self, newsletter_batch, work_dir, user, sample_weekly_trend_insight
    ):
        """대상이 모두 이미 받았는데 발송 완료 표시만 없으면 메일 없이 표시하고 성공한다"""
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict()
        )
        NotiMailLog.objects.create(
            user=user,
            subject=f"벨로그 대시보드 주간 뉴스레터 #{trend.id}",
            is_success=True,
        )

        newsletter_batch.run()

        newsletter_batch.ses_client.send_email.assert_not_called()
        trend.refresh_from_db()
        assert trend.is_processed is True
        assert "✅" in (work_dir / RESULT_FILE).read_text()

    def test_does_not_send_row_that_is_not_this_week(
        self,
        newsletter_batch,
        work_dir,
        user,
        monday,
        sample_weekly_trend_insight,
    ):
        """건너뜀 판정이 이번 주로 보지 않는 행(지난 일요일 전에 끝남)은 보내지 않는다"""
        insight = sample_weekly_trend_insight.to_json_dict()
        insight[BATCH_STATE_KEY] = {
            BATCH_USER_ANALYSIS_COMPLETED: monday.isoformat()
        }
        saturday = monday.date() - timedelta(days=2)
        WeeklyTrend.objects.create(
            week_start_date=saturday - timedelta(days=6),
            week_end_date=saturday,
            insight=insight,
        )

        with pytest.raises(Exception, match="No WeeklyTrend data"):
            newsletter_batch.run()

        newsletter_batch.ses_client.send_email.assert_not_called()

    def test_fails_when_there_are_no_subscribers(
        self, newsletter_batch, work_dir, sample_weekly_trend_insight
    ):
        """구독자가 한 명도 없으면 발송 완료 표시 없이 실패한다"""
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict()
        )

        with pytest.raises(Exception, match="No target users found"):
            newsletter_batch.run()

        trend.refresh_from_db()
        assert trend.is_processed is False
        assert "❌" in (work_dir / RESULT_FILE).read_text()

    def test_marks_newsletter_started_before_first_mail(
        self, newsletter_batch, work_dir, user, sample_weekly_trend_insight
    ):
        """첫 메일을 보내기 전에 이번 주 행에 발송 시작 표시를 남긴다"""
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict()
        )
        started_at_send = []
        newsletter_batch.ses_client.send_email.side_effect = (
            lambda message: started_at_send.append(
                WeeklyTrend.objects.get(pk=trend.pk).batch_value(
                    BATCH_NEWSLETTER_STARTED
                )
            )
        )

        newsletter_batch.run()

        assert len(started_at_send) == 1
        assert started_at_send[0] is not None

    def test_rerun_after_crash_does_not_resend_to_received_emails(
        self,
        newsletter_batch,
        work_dir,
        user,
        create_user,
        sample_weekly_trend_insight,
    ):
        """청크 중간에 프로세스가 죽은 뒤 다시 돌려도 이미 보낸 이메일로는 다시 보내지 않는다"""
        create_user("second@example.com")
        create_user("third@example.com")
        create_this_week_trend(sample_weekly_trend_insight.to_json_dict())
        sent = []

        def send_until_killed(message):
            # 한 청크의 세 번째 메일을 보내다 프로세스가 죽는다
            if len(sent) == 2:
                raise ProcessKilled()
            sent.append(message.to[0])

        newsletter_batch.ses_client.send_email.side_effect = send_until_killed
        with pytest.raises(ProcessKilled):
            newsletter_batch.run()

        # 새 프로세스로 다시 돌린다
        newsletter_batch.ses_client.send_email.side_effect = (
            lambda message: sent.append(message.to[0])
        )
        type(newsletter_batch)(ses_client=newsletter_batch.ses_client).run()

        assert sorted(sent) == [
            "second@example.com",
            "test@example.com",
            "third@example.com",
        ]

    def test_stops_when_mail_log_cannot_be_saved(
        self,
        newsletter_batch,
        work_dir,
        user,
        create_user,
        sample_weekly_trend_insight,
    ):
        """발송 기록을 저장하지 못하면 다음 청크를 보내지 않고 배치를 멈춘다"""
        newsletter_batch.chunk_size = 1
        create_user("other@example.com")
        create_this_week_trend(sample_weekly_trend_insight.to_json_dict())

        with (
            patch.object(
                NotiMailLog.objects,
                "create",
                side_effect=DatabaseError("db down"),
            ),
            pytest.raises(DatabaseError, match="db down"),
        ):
            newsletter_batch.run()

        assert newsletter_batch.ses_client.send_email.call_count == 1

    def test_rechecks_received_emails_before_each_chunk(
        self,
        newsletter_batch,
        work_dir,
        user,
        create_user,
        sample_weekly_trend_insight,
    ):
        """청크마다 보내기 직전에 이미 받은 이메일을 다시 빼서 겹친 실행과 중복 발송하지 않는다"""
        newsletter_batch.chunk_size = 1
        other = create_user("other@example.com")
        trend = create_this_week_trend(
            sample_weekly_trend_insight.to_json_dict()
        )
        subject = f"벨로그 대시보드 주간 뉴스레터 #{trend.id}"

        def send_while_other_run_sends_the_rest(message):
            # 첫 청크를 보내는 사이 겹친 실행이 나머지 사람에게 보냈다
            for target in (user, other):
                if target.email != message.to[0]:
                    NotiMailLog.objects.create(
                        user=target, subject=subject, is_success=True
                    )

        newsletter_batch.ses_client.send_email.side_effect = (
            send_while_other_run_sends_the_rest
        )

        newsletter_batch.run()

        assert newsletter_batch.ses_client.send_email.call_count == 1


@pytest.fixture
def newsletter_main(mock_setup_django):
    # 모듈 맨 위의 import setup_django 를 흉내 낸 뒤에만 불러올 수 있다
    from insight.tasks.weekly_newsletter_batch import main

    return main


@pytest.mark.django_db
class TestWeeklyNewsletterMain:
    @patch("insight.tasks.weekly_newsletter_batch.SESClient")
    def test_removes_last_skip_marker_at_start(
        self, mock_ses_client_cls, newsletter_main, work_dir
    ):
        """시작할 때 지난 실행이 남긴 건너뜀 표시를 지운다"""
        (work_dir / SKIP_MARKER).touch()

        # 이번 주 행이 없어 실패하는 실행
        with pytest.raises(Exception, match="No WeeklyTrend data"):
            newsletter_main()

        assert not (work_dir / SKIP_MARKER).exists()
