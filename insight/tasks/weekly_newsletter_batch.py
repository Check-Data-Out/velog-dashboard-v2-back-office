from datetime import timedelta
import logging
import warnings

from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Count, Sum
import environ
import html2text

import setup_django  # noqa

from noti.models import NotiMailLog
from users.models import User
from insight.models import WeeklyTrend, UserWeeklyTrend
from posts.models import PostDailyStatistics
from utils.utils import get_local_now, to_dict, parse_json

from modules.mail.schemas import AWSSESCredentials, EmailMessage
from modules.mail.ses.client import SESClient
from insight.schemas import (
    WeeklyTrendContext, 
    UserWeeklyTrendContext, 
    NewsletterContext, 
    Newsletter
)


logger = logging.getLogger("newsletter")

# naive datetime 경고 무시
warnings.filterwarnings('ignore', message='.*received a naive datetime.*')

class WeeklyNewsletterBatch:
    def __init__(self, chunk_size: int = 100, max_retry_count: int = 3):
        """
        뉴스레터 배치 발송 클래스 초기화
        
        Args:
            chunk_size: 한 번에 처리할 사용자 수
            max_retry_count: 메일 발송 실패 시 최대 재시도 횟수
        """
        self.env = environ.Env()
        self.chunk_size = chunk_size
        self.max_retry_count = max_retry_count
        self.before_a_week = get_local_now() - timedelta(weeks=1)
        
        try:
            self.ses_client = SESClient.get_client(
                AWSSESCredentials(
                    aws_access_key_id=self.env("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=self.env("AWS_SECRET_ACCESS_KEY"),
                    aws_region_name=self.env("AWS_REGION"),
                )
            )
        except Exception as e:
            logger.error(f"Failed to initialize SES client: {e}")
            raise e from e

    def delete_old_maillogs(self) -> None:
        """
        7일 이전의 성공한 메일 발송 로그 삭제
        삭제 중 실패시에도 계속 진행
        """
        try:
            deleted_count = NotiMailLog.objects.filter(
                created_at__lt=self.before_a_week,
                is_success=True,
            ).delete()[0]
            
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old mail logs")
        except Exception as e:
            logger.error(f"Failed to delete old mail logs: {e}")

    def get_target_user_chunks(self) -> list[list[dict]]:
        """
        뉴스레터 발송 대상 유저 목록을 청크 단위로 조회
        
        Returns:
            target_user_chunks: 청크 단위로 나뉜 사용자 목록
        """
        try:
            target_users = list(User.objects.filter(
                is_active=True,
                email__isnull=False,
            ).values('id', 'email', 'username').distinct())

            target_user_chunks = [
                target_users[i:i + self.chunk_size] 
                for i in range(0, len(target_users), self.chunk_size)
            ]
            
            logger.info(f"Found {len(target_users)} target users in {len(target_user_chunks)} chunks")
            return target_user_chunks
            
        except Exception as e:
            logger.error(f"Failed to get target user chunks: {e}")
            raise e from e

    def render_weekly_trend(self) -> str:
        """
        공통 WeeklyTrend 조회 및 템플릿 적용
        
        Returns:
            렌더링된 주간 트렌드 HTML
            
        Raises:
            Exception: WeeklyTrend 데이터가 없는 경우
        """
        try:
            weekly_trend = WeeklyTrend.objects.filter(
                week_end_date__gte=self.before_a_week,
                is_processed=False,
            ).values('id', 'insight', 'week_start_date', 'week_end_date').first()

            if not weekly_trend:
                logger.error("No WeeklyTrend data, batch stopped")
                raise Exception("No WeeklyTrend data, batch stopped")
            
            # 뉴스레터 상태 저장
            self.weekly_info = {
                'newsletter_order': weekly_trend['id'],
                's_date': weekly_trend['week_start_date'],
                'e_date': weekly_trend['week_end_date'],
            }
        
            context = to_dict(WeeklyTrendContext(insight=parse_json(weekly_trend['insight'])))
            weekly_trend_html = render_to_string('insights/weekly_trend.html', context)

            # 템플릿 렌더링이 제대로 되지 않은 경우
            if '이 주의 트렌딩 글' not in weekly_trend_html or '트렌드 분석' not in weekly_trend_html:
                logger.error(f"Failed to build weekly trend HTML for newsletter #{weekly_trend['id']}")
                raise Exception(f"Failed to build weekly trend HTML for newsletter #{weekly_trend['id']}")
            
            logger.info(f"Generated weekly trend HTML for newsletter #{weekly_trend['id']}")
            return weekly_trend_html
            
        except Exception as e:
            logger.error(f"Failed to get templated weekly trend: {e}")
            raise e from e
    
    def _get_users_weekly_stats(self, user_ids: list[int]) -> dict[int, dict]:
        """
        여러 유저의 주간 통계를 일괄 조회
        
        Args:
            user_ids: 대상 사용자 ID 목록
            
        Returns:
            users_weekly_stats_dict: user_id를 키로 하는 통계 정보 딕셔너리
        """
        try:
            users_weekly_stats = PostDailyStatistics.objects.filter(
                post__user_id__in=user_ids,
                date__gte=self.before_a_week,
            ).values('post__user_id').annotate(
                posts=Count('post', distinct=True),
                views=Sum('daily_view_count'),
                likes=Sum('daily_like_count')
            )
            
            users_weekly_stats_dict = {
                s['post__user_id']: {
                    'posts': s['posts'] or 0,
                    'views': s['views'] or 0,
                    'likes': s['likes'] or 0
                } for s in users_weekly_stats
            }
            
            logger.info(f"Fetched weekly stats for {len(users_weekly_stats_dict)} users out of {len(user_ids)}")
            return users_weekly_stats_dict
            
        except Exception as e:
            logger.error(f"Failed to get users weekly stats: {e}")
            return {}

    def _get_users_weekly_trends(self, user_ids: list[int]) -> dict[int, UserWeeklyTrend]:
        """
        뉴스레터 발송 대상 유저 목록에 대한 UserWeeklyTrend 조회
        
        Args:
            user_ids: 대상 사용자 ID 목록
            
        Returns:
            users_weekly_trends_dict: user_id를 키로 하는 UserWeeklyTrend 딕셔너리
        """
        try:
            user_weekly_trends = UserWeeklyTrend.objects.filter(
                week_end_date__gte=self.before_a_week,
                user_id__in=user_ids,
                is_processed=False,
            ).values('id', 'user_id', 'insight')

            # user_id를 키로 하는 딕셔너리로 변환
            users_weekly_trends_dict = {
                trend['user_id']: UserWeeklyTrend(
                    id=trend['id'],
                    user_id=trend['user_id'],
                    insight=trend['insight']
                ) for trend in user_weekly_trends
            }

            logger.info(f"Found {len(users_weekly_trends_dict)} user weekly trends out of {len(user_ids)}")
            return users_weekly_trends_dict
            
        except Exception as e:
            logger.error(f"Failed to get user weekly trends: {e}")
            return {}
    
    def _get_expired_token_users(self, user_ids: list[int]) -> set[int]:
        """
        토큰 만료된 유저 ID 목록 조회
        오늘 날짜에 통계 데이터가 없는 사용자를 만료된 토큰 사용자로 간주
        
        Args:
            user_ids: 대상 사용자 ID 목록
            
        Returns:
            expired_user_ids: 토큰이 만료된 사용자 ID 집합
        """
        try:
            active_user_ids = PostDailyStatistics.objects.filter(
                post__user_id__in=user_ids,
                date=get_local_now().date()
            ).values_list('post__user_id', flat=True).distinct()

            expired_user_ids = set(user_ids) - set(active_user_ids)
            
            if expired_user_ids:
                logger.info(f"Found {len(expired_user_ids)} users with expired tokens")
            
            return expired_user_ids
            
        except Exception as e:
            logger.error(f"Failed to get expired token users: {e}")
            return set()
    
    def render_newsletter(self, user: dict, weekly_trend_html: str, user_weekly_trend: UserWeeklyTrend | None, user_weekly_stats: dict, is_expired: bool) -> str:
        """
        개별 사용자의 뉴스레터 HTML 렌더링
        
        Args:
            user: 사용자 정보
            weekly_trend_html: 공통 주간 트렌드 HTML
            user_weekly_trend: 사용자별 주간 트렌드 (Optional)
            user_weekly_stats: 사용자별 주간 통계
            is_expired: 토큰 만료 여부
            
        Returns:
            렌더링된 뉴스레터 HTML
        """
        try:
            user_weekly_trend_html = None

            if user_weekly_trend:
                user_weekly_trend_html = render_to_string(
                    'insights/user_weekly_trend.html', 
                    to_dict(UserWeeklyTrendContext(
                        insight=parse_json(user_weekly_trend.insight), 
                        user=user,
                        user_weekly_stats=user_weekly_stats
                    ))
                )

            newsletter_html = render_to_string(
                'insights/index.html', 
                to_dict(NewsletterContext(
                    s_date=self.weekly_info['s_date'], 
                    e_date=self.weekly_info['e_date'], 
                    is_expired_token_user=is_expired,
                    weekly_trend_html=weekly_trend_html, 
                    user_weekly_trend_html=user_weekly_trend_html, 
                ))
            )
            
            return newsletter_html
        except Exception as e:
            logger.error(f"Failed to render newsletter for user {user.get('id')}: {e}")
            raise e from e


    def build_newsletters(self, user_chunk: list[dict], weekly_trend_html: str) -> list[Newsletter]:
        """
        뉴스레터 템플릿 생성 및 target_user_chunk와 매핑된 메일 메시지 생성
        
        Args:
            user_chunk: 대상 사용자 청크
            weekly_trend_html: 공통 주간 트렌드 HTML
            
        Returns:
            email_messages: 생성된 이메일 메시지 목록
        """
        try:
            user_ids = [user['id'] for user in user_chunk]

            # 개인화를 위한 데이터 일괄 조회
            users_weekly_trends_dict = self._get_users_weekly_trends(user_ids)
            users_weekly_stats_dict = self._get_users_weekly_stats(user_ids)
            expired_token_user_ids = self._get_expired_token_users(user_ids)

            newsletters = []
            for user in user_chunk:
                try:
                    user_weekly_trend = users_weekly_trends_dict.get(user['id'])
                    user_weekly_stats = users_weekly_stats_dict.get(user['id'], {'posts': 0, 'views': 0, 'likes': 0})
                    is_expired = user['id'] in expired_token_user_ids

                    html_body = self.render_newsletter(user, weekly_trend_html, user_weekly_trend, user_weekly_stats, is_expired)
                    text_body = html2text.HTML2Text().handle(html_body)
                    
                    newsletter = Newsletter(
                        user_id=user['id'],
                        email_message=EmailMessage(
                            to=[user['email']],
                            from_email=self.env('DEFAULT_FROM_EMAIL'),
                            subject=f"벨로그 대시보드 주간 뉴스레터 #{self.weekly_info['newsletter_order']}",
                            text_body=text_body,
                            html_body=html_body,
                        )
                    )
                    newsletters.append(newsletter)
                    
                except Exception as e:
                    logger.error(f"Failed to build newsletter for user {user.get('id')}: {e}")
                    continue
            
            logger.info(f"Built {len(newsletters)} newsletters out of {len(user_chunk)}")
            return newsletters
            
        except Exception as e:
            logger.error(f"Failed to build newsletters: {e}")
            return []
    
    def send_newsletter(self, newsletters: list[Newsletter]) -> list[str]:
        """
        뉴스레터 발송 (실패시 max_retry_count 만큼 재시도)
        
        Args:
            email_messages: 발송할 이메일 메시지 목록
            
        Returns:
            success_user_ids: 발송 성공한 사용자 ID 목록
        """
        success_user_ids = []
        mail_logs = []
        
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
                    logger.warning(
                        f"Failed to send email to {newsletter.email_message.to[0]} "
                        f"(attempt {failed_count}/{self.max_retry_count}): {e}"
                    )
            
            # bulk_create를 위한 메일 발송 로그 생성
            mail_logs.append(
                NotiMailLog(
                    user_id=newsletter.user_id,
                    subject=newsletter.email_message.subject,
                    body=newsletter.email_message.text_body,
                    is_success=success,
                    sent_at=timezone.now(),
                    error_message=error_message if not success else ""
                )
            )
        
        # 메일 발송 로그 저장
        if mail_logs:
            try:
                NotiMailLog.objects.bulk_create(mail_logs)
            except Exception as e:
                logger.error(f"Failed to save mail logs: {e}")
        
        logger.info(f"Successfully sent {len(success_user_ids)} emails out of {len(newsletters)}")
        return success_user_ids
    
    def update_weekly_trend_result(self) -> None:
        """
        뉴스레터 발송 결과 공통부분(WeeklyTrend) 저장
        """
        try:
            WeeklyTrend.objects.filter(
                id=self.weekly_info['newsletter_order'],
            ).update(
                is_processed=True,
                processed_at=timezone.now(),
            )
            logger.info(f"Updated WeeklyTrend #{self.weekly_info['newsletter_order']} as processed")
            
        except Exception as e:
            logger.error(f"Failed to update weekly trend result: {e}")

    def update_user_weekly_trend_result(self, success_user_ids: list[int]) -> None:
        """
        뉴스레터 발송 결과 개인화된 부분(UserWeeklyTrend) 저장
        
        Args:
            success_user_ids: 발송 성공한 사용자 ID 목록
        """
        try:
            UserWeeklyTrend.objects.filter(
                user_id__in=success_user_ids,
                week_end_date__gte=self.before_a_week,
            ).update(
                is_processed=True,
                processed_at=timezone.now(),
            )
            logger.info(f"Updated {len(success_user_ids)} UserWeeklyTrend records as processed")
            
        except Exception as e:
            logger.error(f"Failed to update user weekly trend result: {e}")

    def run(self) -> None:
        """
        뉴스레터 배치 발송 메인 실행 로직
        """
        logger.info(
            f"Starting weekly newsletter batch process at {get_local_now().isoformat()}"
        )
        start_time = timezone.now()
        
        try:
            # STEP1: 7일 이전의 성공한 메일 발송 로그 삭제
            self.delete_old_maillogs()

            # STEP2: 뉴스레터 발송 대상 유저 목록 조회
            target_user_chunks = self.get_target_user_chunks()
            
            if not target_user_chunks:
                logger.error("No target users found for newsletter, batch stopped")
                raise Exception("No target users found for newsletter, batch stopped")

            # STEP3: 공통 WeeklyTrend 조회 및 템플릿 생성
            weekly_trend_html = self.render_weekly_trend()

            # STEP4: 청크별로 뉴스레터 발송 및 결과 저장
            total_processed = 0
            total_failed = 0

            for chunk_index, user_chunk in enumerate(target_user_chunks, 1):
                logger.info(f"Processing chunk {chunk_index}/{len(target_user_chunks)} ({len(user_chunk)} users)")
                
                try:
                    newsletters = self.build_newsletters(user_chunk, weekly_trend_html)
                    
                    if not newsletters:
                        logger.warning(f"No email messages built for chunk {chunk_index}")
                        continue

                    if self.env.bool('DEBUG', False):
                        logger.info("DEBUG mode: Printing first email content")
                        print(newsletters[0].email_message.text_body)
                        continue
                    else:
                        success_user_ids = self.send_newsletter(newsletters)
                        self.update_user_weekly_trend_result(success_user_ids)
                        total_processed += len(success_user_ids)
                        total_failed += len(newsletters) - len(success_user_ids)
                        
                except Exception as e:
                    logger.error(f"Failed to process chunk {chunk_index}: {e}")
                    continue
                
            # STEP5: 공통 WeeklyTrend Processed 결과 저장
            if not self.env.bool('DEBUG', False):
                self.update_weekly_trend_result()
            
            logger.info(
                f"Newsletter batch process completed in {(timezone.now() - start_time).total_seconds()} seconds."
                f"Processed: {total_processed}, Failed: {total_failed}"
            )
            
        except Exception as e:
            logger.error(f"Newsletter batch process failed: {e}")
            raise e from e


if __name__ == "__main__":
    WeeklyNewsletterBatch().run()