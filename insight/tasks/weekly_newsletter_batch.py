"""
[25.06.26] 뉴스레터 발송 배치 @ooheunda
- 대부분의 DB I/O 및 메서드는 사용자 청크 단위(100명)로 처리됩니다.
- 메일 발송 실패 시 최대 3번까지 재시도합니다.
- Django 및 AWS SES 의존성 있는 배치입니다.
- ./templates/insights/ 경로의 HTML 템플릿을 사용합니다.
- 아래 커맨드로 실행합니다.
  python ./insight/tasks/weekly_newsletter_batch.py
"""

import logging
import warnings
from datetime import timedelta
from time import sleep

import setup_django  # noqa
from django.conf import settings
from django.db.models import Count, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from insight.models import UserWeeklyTrend, WeeklyTrend
from insight.schemas import (
    Newsletter,
    NewsletterContext,
    UserWeeklyTrendContext,
    WeeklyTrendContext,
)
from modules.mail.schemas import AWSSESCredentials, EmailMessage
from modules.mail.ses.client import SESClient
from noti.models import NotiMailLog
from posts.models import PostDailyStatistics
from users.models import User
from utils.utils import (
    get_local_now,
    parse_json,
    strip_html_tags,
    to_dict,
)

logger = logging.getLogger("newsletter")

# naive datetime 경고 무시 (for _get_users_weekly_stats_chunk)
warnings.filterwarnings("ignore", message=".*received a naive datetime.*")


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
        self.before_a_week = get_local_now() - timedelta(weeks=1)
        # 주간 정보를 상태로 관리
        self.weekly_info = {
            "newsletter_id": None,
            "s_date": None,
            "e_date": None,
        }

    def _delete_old_maillogs(self) -> None:
        """7일 이전의 성공한 메일 발송 로그 삭제"""
        try:
            deleted_count = NotiMailLog.objects.filter(
                created_at__lt=self.before_a_week,
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
            raise e from e

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

            # 렌더링. 관리를 위해 dataclass 사용
            context = to_dict(
                WeeklyTrendContext(insight=parse_json(weekly_trend["insight"]))
            )
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
            raise e from e

    def _get_users_weekly_stats_chunk(
        self, user_ids: list[int]
    ) -> tuple[dict[str, dict], set[int]]:
        """유저별 전체 글 주간 통계를 청크 단위로 일괄 조회후 매핑"""
        try:
            # 오늘자 통계 조회
            today_stats = (
                PostDailyStatistics.objects.filter(
                    post__user_id__in=user_ids,
                    date=get_local_now().date(),
                )
                .values("post__user_id")
                .annotate(
                    posts=Count("post", distinct=True),
                    views=Sum("daily_view_count"),
                    likes=Sum("daily_like_count"),
                )
            )

            # 오늘자 통계 없는 유저는 토큰 만료로 간주
            expired_user_ids = set(user_ids) - set(
                today_stats.values_list("post__user_id", flat=True)
            )

            if expired_user_ids:
                logger.info(
                    f"Found {len(expired_user_ids)} users with expired tokens"
                    f"Expired user ids: {expired_user_ids}"
                )

            # 토큰 정상 사용자들의 일주일 전 통계 조회
            before_a_week_stats = (
                PostDailyStatistics.objects.filter(
                    post__user_id__in=set(user_ids) - expired_user_ids,
                    date=self.before_a_week.date(),
                )
                .values("post__user_id")
                .annotate(
                    posts=Count("post", distinct=True),
                    views=Sum("daily_view_count"),
                    likes=Sum("daily_like_count"),
                )
            )

            # 계산 편의성 및 가독성을 위해 딕셔너리로 변경
            before_stats_dict = {
                stat["post__user_id"]: {
                    "posts": stat["posts"] or 0,
                    "views": stat["views"] or 0,
                    "likes": stat["likes"] or 0,
                }
                for stat in before_a_week_stats
            }

            # 일주일간의 변동값 계산 (오늘 통계 - 일주일 전 통계)
            users_weekly_stats_dict = {}
            for stat in today_stats:
                user_id = stat["post__user_id"]
                before_stat = before_stats_dict.get(
                    user_id, {"posts": 0, "views": 0, "likes": 0}
                )
                users_weekly_stats_dict[user_id] = {
                    "posts": stat["posts"] - before_stat["posts"],
                    "views": stat["views"] - before_stat["views"],
                    "likes": stat["likes"] - before_stat["likes"],
                }

            logger.info(
                f"Fetched weekly stats for {len(users_weekly_stats_dict)} users out of {len(user_ids)}"
            )

            return users_weekly_stats_dict, expired_user_ids

        except Exception as e:
            # 개인 통계 조회 실패 시에도 계속 진행
            logger.error(f"Failed to get users weekly stats: {e}")
            return {}, set()

    def _get_users_weekly_trend_chunk(
        self, user_ids: list[int]
    ) -> dict[int, UserWeeklyTrend]:
        """여러 유저의 UserWeeklyTrend 일괄 조회 후 매핑"""
        try:
            user_weekly_trends = UserWeeklyTrend.objects.filter(
                week_end_date__gte=self.before_a_week,
                user_id__in=user_ids,
                is_processed=False,
            ).values("id", "user_id", "insight")

            # user_id를 키로 하는 딕셔너리로 변환 (매핑)
            users_weekly_trends_dict = {
                trend["user_id"]: UserWeeklyTrend(
                    id=trend["id"],
                    user_id=trend["user_id"],
                    insight=trend["insight"],
                )
                for trend in user_weekly_trends
            }

            logger.info(
                f"Found {len(users_weekly_trends_dict)} user weekly trends out of {len(user_ids)}"
            )
            return users_weekly_trends_dict

        except Exception as e:
            # 개인 트렌딩 조회 실패 시에도 계속 진행
            logger.error(f"Failed to get user weekly trends: {e}")
            return {}

    def _get_personalized_newsletter_html(
        self,
        user: dict,
        weekly_trend_html: str,
        user_weekly_trend: UserWeeklyTrend | None,
        user_weekly_stats: dict,
        is_expired: bool,
    ) -> str:
        """개별 사용자의 뉴스레터 HTML 렌더링"""
        try:
            user_weekly_trend_html = None

            # 개인 인사이트 데이터 있으면 렌더링
            if user_weekly_trend:
                user_weekly_trend_html = render_to_string(
                    "insights/user_weekly_trend.html",
                    to_dict(
                        UserWeeklyTrendContext(
                            insight=parse_json(user_weekly_trend.insight),
                            user=user,
                            user_weekly_stats=user_weekly_stats,
                        )
                    ),
                )

            # 뉴스레터 최종 렌더링
            newsletter_html = render_to_string(
                "insights/index.html",
                to_dict(
                    NewsletterContext(
                        s_date=self.weekly_info["s_date"],
                        e_date=self.weekly_info["e_date"],
                        is_expired_token_user=is_expired,
                        weekly_trend_html=weekly_trend_html,
                        user_weekly_trend_html=user_weekly_trend_html,
                    )
                ),
            )

            return newsletter_html
        except Exception as e:
            logger.error(
                f"Failed to render newsletter for user {user.get('id')}: {e}"
            )
            raise e from e

    def _build_newsletters(
        self, user_chunk: list[dict], weekly_trend_html: str
    ) -> list[Newsletter]:
        """user_chunk의 user_id로 매핑된 뉴스레터 객체 생성"""
        try:
            user_ids = [user["id"] for user in user_chunk]
            newsletters = []

            # 개인화를 위한 데이터 일괄 조회
            users_weekly_trends_chunk = self._get_users_weekly_trend_chunk(
                user_ids
            )
            users_weekly_stats_chunk, expired_token_user_ids = (
                self._get_users_weekly_stats_chunk(user_ids)
            )

            for user in user_chunk:
                try:
                    # user_id 키의 딕셔너리에서 개인 데이터 조회
                    user_weekly_trend = users_weekly_trends_chunk.get(
                        user["id"]
                    )
                    user_weekly_stats = users_weekly_stats_chunk.get(
                        user["id"]
                    )
                    is_expired = user["id"] in expired_token_user_ids

                    # 뉴스레터 템플릿 렌더링
                    html_body = self._get_personalized_newsletter_html(
                        user=user,
                        weekly_trend_html=weekly_trend_html,
                        user_weekly_trend=user_weekly_trend,
                        user_weekly_stats=user_weekly_stats,
                        is_expired=is_expired,
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
        mail_logs = []  # 메일 발송 로그 일괄 저장을 위한 리스트

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
                        sent_at=timezone.now(),
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
                processed_at=timezone.now(),
            )
            logger.info(
                f"Updated WeeklyTrend #{self.weekly_info['newsletter_id']} as processed"
            )

        except Exception as e:
            logger.error(f"Failed to update weekly trend result: {e}")
            raise e from e

    def _update_user_weekly_trend_results(
        self, success_user_ids: list[int]
    ) -> None:
        """개별 부분(UserWeeklyTrend) 발송 결과 일괄 저장"""
        try:
            UserWeeklyTrend.objects.filter(
                user_id__in=success_user_ids,
                week_end_date__gte=self.before_a_week,
            ).update(
                is_processed=True,
                processed_at=timezone.now(),
            )
            logger.info(
                f"Updated {len(success_user_ids)} UserWeeklyTrend records as processed"
            )

        except Exception as e:
            # 개인 트렌딩 업데이트 실패 시에도 계속 진행
            logger.error(f"Failed to update user weekly trend result: {e}")

    def run(self) -> None:
        """뉴스레터 배치 발송 메인 실행 로직"""
        logger.info(
            f"Starting weekly newsletter batch process at {get_local_now().isoformat()}"
        )
        start_time = timezone.now()
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

            if total_processed > total_failed:
                # 과반수 이상 성공시에만 processed로 마킹
                self._update_weekly_trend_result()
                logger.info(
                    f"Newsletter batch process completed successfully in {(timezone.now() - start_time).total_seconds()} seconds. "
                    f"Processed: {total_processed}, Failed: {total_failed}, Success Rate: {success_rate:.2%}"
                )
            else:
                logger.warning(
                    f"Newsletter batch process failed to meet success criteria in {(timezone.now() - start_time).total_seconds()} seconds. "
                    f"Processed: {total_processed}, Failed: {total_failed}, Success Rate: {success_rate:.2%}. "
                    f"WeeklyTrend remains unprocessed due to low success rate (< 50%)"
                )

        except Exception as e:
            logger.error(f"Newsletter batch process failed: {e}")
            raise e from e


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
        raise e from e

    # 배치 실행
    WeeklyNewsletterBatch(ses_client=ses_client).run()
