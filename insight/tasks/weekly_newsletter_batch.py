"""
[25.06.26] 뉴스레터 발송 배치 @ooheunda
- 대부분의 DB I/O 및 메서드는 사용자 청크 단위(100명)로 처리됩니다.
- 메일 발송 실패 시 최대 3번까지 재시도합니다.
- Django 및 AWS SES 의존성 있는 배치입니다.
- ./templates/insights/ 경로의 HTML 템플릿을 사용합니다.
- 아래 커맨드로 실행합니다.
- poetry run python ./insight/tasks/weekly_newsletter_batch.py

[25.07.13] 뉴스레터 발송 배치 소소한 수정 (작성자: 정현우)
- 전체적인 DTO 정리, 주간 사용자 분석 배치에서 만드는 데이터셋과 메일에 필요한 데이터셋 전체 통일
"""

import logging
from datetime import timedelta
from time import sleep

import setup_django  # noqa
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string

from insight.models import (
    UserWeeklyTrend,
    WeeklyTrend,
    WeeklyTrendInsight,
    WeeklyUserTrendInsight,
)
from insight.schemas import Newsletter, NewsletterContext
from modules.mail.schemas import AWSSESCredentials, EmailMessage
from modules.mail.ses.client import SESClient
from noti.models import NotiMailLog
from users.models import User
from utils.utils import (
    from_dict,
    get_local_date,
    get_local_now,
    strip_html_tags,
    to_dict,
)

logger = logging.getLogger("newsletter")


class WeeklyNewsletterBatch:
    def __init__(
        self,
        ses_client: SESClient,
        chunk_size: int = 100,
        max_retry_count: int = 3,
    ):
        """
        클래스 초기화

        Args:
            ses_client: SESClient 인스턴스
            chunk_size: 한 번에 처리할 사용자 수
            max_retry_count: 메일 발송 실패 시 최대 재시도 횟수
        """
        self.ses_client = ses_client
        self.chunk_size = chunk_size
        self.max_retry_count = max_retry_count
        # 주간 정보를 상태로 관리
        self.weekly_info = {
            "newsletter_id": None,
            "s_date": None,
            "e_date": None,
        }
        # 배치 실행 시점 기준의 local 날짜 로드
        self.before_a_week = get_local_date() - timedelta(weeks=1)
        self.today = get_local_date()

    def _delete_old_maillogs(self) -> None:
        """이전 뉴스레터의 성공한 메일 발송 로그 삭제"""
        try:
            deleted_count = NotiMailLog.objects.filter(
                # 느슨한 시간 적용
                sent_at__lt=self.before_a_week + timedelta(days=1),
                is_success=True,
            ).delete()[0]

            logger.info(f"Deleted {deleted_count} old mail logs")
        except Exception as e:
            # 삭제 실패 시에도 계속 진행
            logger.error(f"Failed to delete old mail logs: {e}")

    def _get_target_user_chunks(self) -> list[list[dict]]:
        """뉴스레터 발송 대상 유저 목록 조회 후 청크 단위로 분할"""
        try:
            target_users = list(
                User.objects.filter(
                    is_active=True,
                    email__isnull=False,
                )
                .values("id", "email", "username")
                .distinct("email")
            )

            target_user_chunks = [
                target_users[i : i + self.chunk_size]
                for i in range(0, len(target_users), self.chunk_size)
            ]

            logger.info(
                f"Found {len(target_users)} target users in {len(target_user_chunks)} chunks"
            )
            return target_user_chunks

        except Exception as e:
            logger.error(f"Failed to get target user chunks: {e}")
            raise

    def _get_weekly_trend_html(self) -> str:
        """공통 WeeklyTrend 조회 및 템플릿 렌더링 (1회만 수행)"""
        try:
            weekly_trend = (
                WeeklyTrend.objects.filter(
                    week_end_date__gte=self.before_a_week,
                    is_processed=False,
                )
                .values("id", "insight", "week_start_date", "week_end_date")
                .first()
            )

            # 트렌딩 인사이트 데이터 (공통) 없을 시 배치 종료
            if not weekly_trend:
                logger.error("No WeeklyTrend data, batch stopped")
                raise Exception("No WeeklyTrend data, batch stopped")

            # 주간 정보 상태 저장
            self.weekly_info = {
                "newsletter_id": weekly_trend["id"],
                "s_date": weekly_trend["week_start_date"],
                "e_date": weekly_trend["week_end_date"],
            }

            # dataclass로 변환 & 벨리데이션
            weekly_trend_insight = from_dict(
                WeeklyTrendInsight, weekly_trend["insight"]
            )
            context = {"insight": weekly_trend_insight.to_dict()}
            weekly_trend_html = render_to_string(
                "insights/weekly_trend.html", context
            )

            # 템플릿 렌더링이 제대로 되지 않은 경우 배치 종료
            if (
                "이 주의 트렌딩 글" not in weekly_trend_html
                or "트렌드 분석" not in weekly_trend_html
            ):
                logger.error(
                    f"Failed to build weekly trend HTML for newsletter #{weekly_trend['id']}"
                )
                raise Exception(
                    f"Failed to build weekly trend HTML for newsletter #{weekly_trend['id']}"
                )

            logger.info(
                f"Generated weekly trend HTML for newsletter #{weekly_trend['id']}"
            )
            return weekly_trend_html

        except Exception as e:
            logger.error(f"Failed to get templated weekly trend: {e}")
            raise

    def _get_users_weekly_trend_chunk(
        self, user_ids: list[int]
    ) -> dict[int, WeeklyUserTrendInsight]:
        """여러 유저의 UserWeeklyTrend 일괄 조회 후 매핑"""
        try:
            user_weekly_trends = UserWeeklyTrend.objects.filter(
                week_end_date__gte=self.before_a_week,
                user_id__in=user_ids,
                is_processed=False,
            ).values("user_id", "insight")

            # user_id를 키로 하는 딕셔너리로 변환 (매핑)
            users_weekly_trends_dict = {}
            for trend in user_weekly_trends:
                # dataclass로 변환
                insight_data = from_dict(
                    WeeklyUserTrendInsight, trend["insight"]
                )
                users_weekly_trends_dict[trend["user_id"]] = insight_data

            logger.info(
                f"Found {len(users_weekly_trends_dict)} user weekly trends out of {len(user_ids)}"
            )
            return users_weekly_trends_dict

        except Exception as e:
            # 개인 트렌딩 조회 실패 시에도 계속 진행
            logger.error(f"Failed to get user weekly trends: {e}")
            return {}

    def _get_user_weekly_trend_html(
        self,
        user: dict,
        user_weekly_trend: WeeklyUserTrendInsight | None,
    ) -> str:
        """유저 개인 트렌드 렌더링"""
        try:
            user_weekly_trend_html = render_to_string(
                "insights/user_weekly_trend.html",
                {
                    "user": user,
                    "insight": (
                        user_weekly_trend.to_dict()
                        if user_weekly_trend
                        else None
                    ),
                },
            )

            return user_weekly_trend_html
        except Exception as e:
            logger.error(
                f"Failed to render newsletter for user {user.get('id')}: {e}"
            )
            raise

    def _get_newsletter_html(
        self,
        is_expired_token_user: bool,
        weekly_trend_html: str,
        user_weekly_trend_html: str | None,
    ) -> str:
        """최종 뉴스레터 렌더링"""
        try:
            newsletter_html = render_to_string(
                "insights/index.html",
                to_dict(
                    NewsletterContext(
                        s_date=self.weekly_info["s_date"],
                        e_date=self.weekly_info["e_date"],
                        is_expired_token_user=is_expired_token_user,
                        weekly_trend_html=weekly_trend_html,
                        user_weekly_trend_html=user_weekly_trend_html,
                    )
                ),
            )

            return newsletter_html
        except Exception as e:
            logger.error(f"Failed to render newsletter html: {e}")
            raise

    def _build_newsletters(
        self, user_chunk: list[dict], weekly_trend_html: str
    ) -> list[Newsletter]:
        """user_chunk의 user_id로 매핑된 뉴스레터 객체 생성"""
        try:
            user_ids = [user["id"] for user in user_chunk]
            newsletters = []

            # 개인화를 위한 데이터 일괄 조회
            # users_weekly_trends_chunk 의 index 가 user_pk & value 가 WeeklyUserTrendInsight
            users_weekly_trends_chunk = self._get_users_weekly_trend_chunk(
                user_ids
            )

            # insight_userweeklytrend가 없는 유저는 토큰 만료 유저로 간주
            expired_token_user_ids = set(user_ids) - set(
                users_weekly_trends_chunk.keys()
            )

            if expired_token_user_ids:
                logger.info(
                    f"Found {len(expired_token_user_ids)} users with expired tokens, "
                    f"Expired user ids: {list(expired_token_user_ids)}"
                )

            # 유저별 뉴스레터 객체 생성
            for user in user_chunk:
                try:
                    # user_id 키의 딕셔너리에서 개인 데이터 조회
                    user_weekly_trend = users_weekly_trends_chunk.get(
                        user["id"]
                    )
                    is_expired_token_user = (
                        user["id"] in expired_token_user_ids
                    )

                    # 토큰 정상 사용자만 개인 트렌드 렌더링
                    user_weekly_trend_html = None
                    if not is_expired_token_user:
                        user_weekly_trend_html = (
                            self._get_user_weekly_trend_html(
                                user=user,
                                user_weekly_trend=user_weekly_trend,
                            )
                        )

                    # 최종 뉴스레터 렌더링
                    html_body = self._get_newsletter_html(
                        is_expired_token_user=is_expired_token_user,
                        weekly_trend_html=weekly_trend_html,
                        user_weekly_trend_html=user_weekly_trend_html,
                    )
                    text_body = strip_html_tags(html_body)

                    # 뉴스레터 객체 생성
                    newsletter = Newsletter(
                        user_id=user["id"],
                        email_message=EmailMessage(  # SES 발송 객체
                            to=[user["email"]],
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            subject=f"벨로그 대시보드 주간 뉴스레터 #{self.weekly_info['newsletter_id']}",
                            text_body=text_body,
                            html_body=html_body,
                        ),
                    )
                    newsletters.append(newsletter)

                except Exception as e:
                    # 개인 build 실패해도 청크는 계속 진행
                    logger.error(
                        f"Failed to build newsletter for user {user.get('id')}: {e}"
                    )
                    continue

            logger.info(
                f"Built {len(newsletters)} newsletters out of {len(user_chunk)}"
            )
            return newsletters

        except Exception as e:
            # 빌드 실패 시 빈 목록 반환해 계속 진행
            logger.error(f"Failed to build newsletters: {e}")
            return []

    def _send_newsletters(self, newsletters: list[Newsletter]) -> list[int]:
        """뉴스레터 발송 (실패시 max_retry_count 만큼 재시도)"""
        success_user_ids = []
        mail_logs = []

        # 개별 뉴스레터 발송
        for newsletter in newsletters:
            success = False
            failed_count = 0
            error_message = ""

            # 최대 max_retry_count 만큼 메일 발송
            while failed_count < self.max_retry_count and not success:
                try:
                    self.ses_client.send_email(newsletter.email_message)
                    success = True
                    success_user_ids.append(newsletter.user_id)

                except Exception as e:
                    failed_count += 1
                    error_message = str(e)
                    logger.error(
                        f"Failed to send newsletter to (id: {newsletter.user_id} email: {newsletter.email_message.to[0]}) "
                        f"(attempt {failed_count}/{self.max_retry_count}): {e}"
                    )
                    # 재시도 전 대기
                    if failed_count != self.max_retry_count:
                        sleep(failed_count)

            try:
                # bulk_create를 위한 메일 발송 로그 생성
                mail_logs.append(
                    NotiMailLog(
                        user_id=newsletter.user_id,
                        subject=newsletter.email_message.subject,
                        body=newsletter.email_message.text_body,
                        is_success=success,
                        sent_at=get_local_now(),
                        error_message=error_message if not success else "",
                    )
                )
            except Exception as e:
                # 로그 생성 실패해도 청크는 계속 진행
                logger.error(f"Failed to create NotiMailLog object: {e}")
                continue

        # 메일 발송 로그 저장
        if mail_logs:
            try:
                NotiMailLog.objects.bulk_create(mail_logs)
            except Exception as e:
                # 저장 실패 시에도 계속 진행
                logger.error(f"Failed to save mail logs: {e}")

        logger.info(
            f"Successfully sent {len(success_user_ids)} newsletters out of {len(newsletters)}"
        )
        return success_user_ids

    def _update_weekly_trend_result(self) -> None:
        """공통 부분(WeeklyTrend) 발송 결과 저장"""
        try:
            WeeklyTrend.objects.filter(
                id=self.weekly_info["newsletter_id"],
            ).update(
                is_processed=True,
                processed_at=get_local_now(),
            )
            logger.info(
                f"Updated WeeklyTrend #{self.weekly_info['newsletter_id']} as processed"
            )

        except Exception as e:
            logger.error(f"Failed to update weekly trend result: {e}")
            raise

    def _update_user_weekly_trend_results(
        self, success_user_ids: list[int]
    ) -> None:
        """개별 부분(UserWeeklyTrend) 발송 결과 일괄 저장"""
        try:
            with transaction.atomic():
                updated_count = UserWeeklyTrend.objects.filter(
                    user_id__in=success_user_ids,
                    week_end_date__gte=self.before_a_week,
                ).update(
                    is_processed=True,
                    processed_at=get_local_now(),
                )
            logger.info(
                f"Updated {updated_count} UserWeeklyTrend records as processed"
            )

        except Exception as e:
            # 개인 트렌딩 업데이트 실패 시에도 계속 진행
            logger.error(f"Failed to update user weekly trend result: {e}")

    def run(self) -> None:
        """뉴스레터 배치 발송 메인 실행 로직"""
        logger.info(
            f"Starting weekly newsletter batch process at {get_local_now().isoformat()}. "
            f"This week's date: {self.before_a_week} ~ {self.today}"
        )
        start_time = get_local_now()
        total_processed = 0
        total_failed = 0

        try:
            # ========================================================== #
            # STEP1: 토큰이 유효성 체크 및 업데이트. 이후 사용자 정보 업데이트
            # ========================================================== #
            self._delete_old_maillogs()

            # ========================================================== #
            # STEP2: 뉴스레터 발송 대상 유저 목록 조회
            # ========================================================== #
            target_user_chunks = self._get_target_user_chunks()

            # 대상 유저 없을 시 배치 종료
            if not target_user_chunks:
                logger.error(
                    "No target users found for newsletter, batch stopped"
                )
                raise Exception(
                    "No target users found for newsletter, batch stopped"
                )

            # ========================================================== #
            # STEP3: 공통 WeeklyTrend 조회 및 템플릿 생성
            # ========================================================== #
            weekly_trend_html = self._get_weekly_trend_html()

            # 로컬 환경에선 뉴스레터 발송 건너뜀
            if settings.DEBUG:
                logger.info("DEBUG mode: Skipping newsletter sending")
                return

            # ========================================================== #
            # STEP4: 청크별로 뉴스레터 발송 및 결과 저장
            # ========================================================== #
            for chunk_index, user_chunk in enumerate(target_user_chunks, 1):
                logger.info(
                    f"Processing chunk {chunk_index}/{len(target_user_chunks)} ({len(user_chunk)} users)"
                )

                try:
                    # 해당 청크에 대한 뉴스레터 객체 일괄 생성
                    # 토큰 만료로 판단되는 경우 user_weekly_trend_html 가 None
                    newsletters = self._build_newsletters(
                        user_chunk, weekly_trend_html
                    )

                    # 발송할 뉴스레터 없을 시 다음 청크로
                    if not newsletters:
                        logger.warning(
                            f"No newsletters built for chunk {chunk_index}"
                        )
                        continue

                    # 해당 청크에 대한 뉴스레터 일괄 발송 및 결과 업데이트
                    success_user_ids = self._send_newsletters(newsletters)
                    self._update_user_weekly_trend_results(success_user_ids)

                    # 로깅을 위한 발송 결과 카운트
                    total_processed += len(success_user_ids)
                    total_failed += len(newsletters) - len(success_user_ids)

                except Exception as e:
                    # 예외 발생해도 다음 청크 진행
                    logger.error(f"Failed to process chunk {chunk_index}: {e}")
                    continue

            # ========================================================== #
            # STEP5: 공통 WeeklyTrend Processed 결과 저장 및 로깅
            # ========================================================== #
            success_rate = (
                total_processed / (total_processed + total_failed)
                if (total_processed + total_failed) > 0
                else 0
            )
            elapsed_time = (get_local_now() - start_time).total_seconds()

            if total_processed > total_failed:
                # 과반수 이상 성공시에만 processed로 마킹
                self._update_weekly_trend_result()
                logger.info(
                    f"Newsletter batch process completed successfully in {elapsed_time} seconds. "
                    f"Processed: {total_processed}, Failed: {total_failed}, Success Rate: {success_rate:.2%}"
                )
            else:
                logger.warning(
                    f"Newsletter batch process failed to meet success criteria in {elapsed_time} seconds. "
                    f"Processed: {total_processed}, Failed: {total_failed}, Success Rate: {success_rate:.2%}. "
                    f"WeeklyTrend remains unprocessed due to low success rate (< 50%)"
                )

            # 결과 파일 저장 (for slack notification)
            try:
                with open("newsletter_batch_result.txt", "w") as f:
                    f.write(
                        f"✅ 뉴스레터 발송 완료: 성공 {total_processed}명, 실패 {total_failed}명\\n"
                    )
                    f.write(f"   - 소요 시간: {elapsed_time}초\\n")
                    f.write(f"   - 성공률: {success_rate:.2%}\\n")
            except Exception as e:
                logger.error(f"Failed to save newsletter batch result: {e}")

        except Exception as e:
            logger.error(f"Newsletter batch process failed: {e}")
            try:
                with open("newsletter_batch_result.txt", "w") as f:
                    f.write(f"❌ 뉴스레터 발송 실패: {e}")
            except Exception as e:
                logger.error(f"Failed to save newsletter batch result: {e}")

            raise


if __name__ == "__main__":
    # SES 클라이언트 초기화
    try:
        aws_credentials = AWSSESCredentials(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_region_name=settings.AWS_REGION,
        )

        ses_client = SESClient.get_client(aws_credentials)
    except Exception as e:
        logger.error(
            f"Failed to initialize SES client for sending newsletter: {e}"
        )
        raise

    # 배치 실행
    WeeklyNewsletterBatch(ses_client=ses_client).run()
