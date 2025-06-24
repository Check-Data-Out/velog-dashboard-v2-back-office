from datetime import timedelta
import logging
import sys
from django.template.loader import render_to_string
from django.utils import timezone
import environ
import html2text
from django.db.models import Count, Sum

import setup_django  # noqa

from noti.models import NotiMailLog
from users.models import User
from insight.models import WeeklyTrend, UserWeeklyTrend
from posts.models import PostDailyStatistics
from utils.utils import get_local_now, to_dict

from modules.mail.schemas import AWSSESCredentials, EmailMessage
from modules.mail.ses.client import SESClient
from insight.schemas import WeeklyTrendContext, UserWeeklyTrendContext, NewsletterContext

logger = logging.getLogger("newsletter")

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

    def get_templated_weekly_trend(self) -> str:
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
            
            # 뉴스레터 정보 저장
            self.weekly_info = {
                'newsletter_order': weekly_trend['id'],
                's_date': weekly_trend['week_start_date'],
                'e_date': weekly_trend['week_end_date'],
            }
        
            weekly_trend_html = render_to_string(
                'insights/weekly_trend.html', 
                to_dict(WeeklyTrendContext(insight=weekly_trend['insight']))
            )
            
            logger.info(f"Generated weekly trend HTML for newsletter #{weekly_trend['id']}")
            return weekly_trend_html
            
        except Exception as e:
            logger.error(f"Failed to get templated weekly trend: {e}")
            raise e from e
    
    def get_users_weekly_stats(self, user_ids: list[int]) -> dict[int, dict]:
        """
        여러 유저의 주간 통계를 일괄 조회
        
        Args:
            user_ids: 대상 사용자 ID 목록
            
        Returns:
            stats_dict: user_id를 키로 하는 통계 정보 딕셔너리
        """
        try:
            stats = PostDailyStatistics.objects.filter(
                post__user_id__in=user_ids,
                date__gte=self.before_a_week,
            ).values('post__user_id').annotate(
                posts=Count('post', distinct=True),
                views=Sum('daily_view_count'),
                likes=Sum('daily_like_count')
            )
            
            stats_dict = {
                s['post__user_id']: {
                    'posts': s['posts'] or 0,
                    'views': s['views'] or 0,
                    'likes': s['likes'] or 0
                } for s in stats
            }
            
            logger.info(f"Fetched weekly stats for {len(stats_dict)} users out of {len(user_ids)}")
            return stats_dict
            
        except Exception as e:
            logger.error(f"Failed to get users weekly stats: {e}")
            return {}

    def get_user_weekly_trends(self, user_chunk: list[dict]) -> dict[int, UserWeeklyTrend]:
        """
        뉴스레터 발송 대상 유저 목록에 대한 UserWeeklyTrend 조회
        
        Args:
            user_chunk: 대상 사용자 청크
            
        Returns:
            user_weekly_trends_dict: user_id를 키로 하는 UserWeeklyTrend 딕셔너리
        """
        try:
            user_ids = [user['id'] for user in user_chunk]
            user_weekly_trends = UserWeeklyTrend.objects.filter(
                week_end_date__gte=self.before_a_week,
                user_id__in=user_ids,
                is_processed=False,
            ).values('id', 'user_id', 'insight')

            # user_id를 키로 하는 딕셔너리로 변환
            user_weekly_trends_dict = {
                trend['user_id']: UserWeeklyTrend(
                    id=trend['id'],
                    user_id=trend['user_id'],
                    insight=trend['insight']
                ) for trend in user_weekly_trends
            }
            
            logger.info(f"Found {len(user_weekly_trends_dict)} user weekly trends for chunk")
            return user_weekly_trends_dict
            
        except Exception as e:
            logger.error(f"Failed to get user weekly trends: {e}")
            return {}
    
    def get_expired_token_users(self, user_chunk: list[dict]) -> set[int]:
        """
        토큰 만료된 유저 ID 목록 조회
        오늘 날짜에 통계 데이터가 없는 사용자를 만료된 토큰 사용자로 간주
        
        Args:
            user_chunk: 대상 사용자 청크
            
        Returns:
            expired_user_ids: 토큰이 만료된 사용자 ID 집합
        """
        try:
            user_ids = [user['id'] for user in user_chunk]
            
            active_user_ids = PostDailyStatistics.objects.filter(
                post__user_id__in=user_ids,
                date=timezone.now(),
            ).values_list('post__user_id', flat=True).distinct()
            
            expired_user_ids = set(user_ids) - set(active_user_ids)
            
            if expired_user_ids:
                logger.info(f"Found {len(expired_user_ids)} users with expired tokens")
            
            return expired_user_ids
            
        except Exception as e:
            logger.error(f"Failed to get expired token users: {e}")
            return set()

    def build_email_messages(self, user_chunk: list[dict], weekly_trend_html: str) -> list[EmailMessage]:
        """
        뉴스레터 템플릿 생성 및 target_user_chunk와 매핑된 메일 메시지 생성
        
        Args:
            user_chunk: 대상 사용자 청크
            weekly_trend_html: 공통 주간 트렌드 HTML
            
        Returns:
            email_messages: 생성된 이메일 메시지 목록
        """
        try:
            user_weekly_trends_dict = self.get_user_weekly_trends(user_chunk)
            expired_token_user_ids = self.get_expired_token_users(user_chunk)
            
            # 청크 단위로 일괄 통계 조회
            user_ids = [user['id'] for user in user_chunk]
            users_weekly_stats = self.get_users_weekly_stats(user_ids)

            email_messages = []
            for user in user_chunk:
                try:
                    user_weekly_trend = user_weekly_trends_dict.get(user['id'])
                    user_weekly_trend_html = None

                    if user_weekly_trend:
                        user_weekly_stats = users_weekly_stats.get(user['id'], {'posts': 0, 'views': 0, 'likes': 0})
                        
                        user_weekly_trend_html = render_to_string(
                            'insights/user_weekly_trend.html', 
                            to_dict(UserWeeklyTrendContext(
                                insight=user_weekly_trend.insight, 
                                user=user,
                                user_weekly_stats=user_weekly_stats
                            ))
                        )
                    
                    is_expired = user['id'] in expired_token_user_ids
                    
                    html_body = render_to_string(
                        'insights/index.html', 
                        to_dict(NewsletterContext(
                            s_date=self.weekly_info['s_date'], 
                            e_date=self.weekly_info['e_date'], 
                            is_expired_token_user=is_expired,
                            weekly_trend_html=weekly_trend_html, 
                            user_weekly_trend_html=user_weekly_trend_html, 
                        ))
                    )
                    text_body = html2text.HTML2Text().handle(html_body)
                    
                    email_message = EmailMessage(
                        to=[user['email']],
                        from_email=self.env('DEFAULT_FROM_EMAIL'),
                        subject=f"벨로그 대시보드 주간 뉴스레터 #{self.weekly_info['newsletter_order']}",
                        text_body=text_body,
                        html_body=html_body,
                    )
                    email_messages.append(email_message)
                    
                except Exception as e:
                    logger.error(f"Failed to build email message for user {user.get('id')}: {e}")
                    continue
            
            logger.info(f"Built {len(email_messages)} email messages for chunk")
            return email_messages
            
        except Exception as e:
            logger.error(f"Failed to build email messages: {e}")
            return []
    
    def send_newsletter(self, email_messages: list[EmailMessage]) -> list[str]:
        """
        뉴스레터 발송 (max_retry_count 만큼 재시도)
        
        Args:
            email_messages: 발송할 이메일 메시지 목록
            
        Returns:
            success_user_emails: 발송 성공한 사용자 이메일 목록
        """
        success_user_emails = []
        
        for email_message in email_messages:
            failed_count = 0
            success = False
            
            while failed_count < self.max_retry_count and not success:
                try:
                    self.ses_client.send_email(email_message)
                    success = True
                    success_user_emails.append(email_message.to[0])
                    logger.debug(f"Successfully sent email to {email_message.to[0]}")
                    
                except Exception as e:
                    failed_count += 1
                    logger.warning(
                        f"Failed to send email to {email_message.to[0]} "
                        f"(attempt {failed_count}/{self.max_retry_count}): {e}"
                    )
                                
            if not success:
                logger.error(f"Failed to send email to {email_message.to[0]} after {self.max_retry_count} attempts")
        
        if success_user_emails:
            logger.info(f"Successfully sent {len(success_user_emails)} emails out of {len(email_messages)}")
        else:
            logger.warning(f"Failed to send {len(email_messages) - len(success_user_emails)} emails out of {len(email_messages)}")
            
        return success_user_emails
    
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

    def update_user_weekly_trend_result(self, user_chunk: list[dict], success_user_emails: list[str]) -> None:
        """
        뉴스레터 발송 결과 개인화된 부분(UserWeeklyTrend) 저장
        
        Args:
            user_chunk: 대상 사용자 청크
            success_user_emails: 발송 성공한 사용자 이메일 목록
        """
        try:
            success_user_ids = [user['id'] for user in user_chunk if user['email'] in success_user_emails]
            if success_user_ids:
                UserWeeklyTrend.objects.filter(
                    user_id__in=success_user_ids,
                    week_end_date__gte=self.before_a_week,
                ).update(
                    is_processed=True,
                    processed_at=timezone.now(),
                )
                logger.info(f"Updated {len(success_user_ids)} UserWeeklyTrend records as processed")
            else:
                logger.warning("No successful email sends to update UserWeeklyTrend")
                
        except Exception as e:
            logger.error(f"Failed to update user weekly trend result: {e}")

    def run(self) -> None:
        """
        뉴스레터 배치 발송 메인 실행 로직
        """
        logger.info(
            f"Starting weekly newsletter batch process at {get_local_now().isoformat()}"
        )
        
        try:
            # STEP1: 7일 이전의 성공한 메일 발송 로그 삭제
            self.delete_old_maillogs()

            # STEP2: 뉴스레터 발송 대상 유저 목록 조회
            target_user_chunks = self.get_target_user_chunks()
            
            if not target_user_chunks:
                logger.warning("No target users found for newsletter")
                return

            # STEP3: 공통 WeeklyTrend 조회 및 템플릿 생성
            weekly_trend_html = self.get_templated_weekly_trend()

            # STEP4: 청크별로 뉴스레터 발송 및 결과 저장
            total_processed = 0
            total_failed = 0
            
            for chunk_index, user_chunk in enumerate(target_user_chunks, 1):
                logger.info(f"Processing chunk {chunk_index}/{len(target_user_chunks)} ({len(user_chunk)} users)")
                
                try:
                    email_messages = self.build_email_messages(user_chunk, weekly_trend_html)
                    
                    if not email_messages:
                        logger.warning(f"No email messages built for chunk {chunk_index}")
                        continue

                    if self.env.bool('DEBUG', False):
                        logger.info("DEBUG mode: Printing first email content")
                        print(email_messages[0].text_body)
                        continue
                    else:
                        success_user_emails = self.send_newsletter(email_messages)
                        self.update_user_weekly_trend_result(user_chunk, success_user_emails)
                        
                        total_processed += len(success_user_emails)
                        total_failed += len(email_messages) - len(success_user_emails)
                        
                except Exception as e:
                    logger.error(f"Failed to process chunk {chunk_index}: {e}")
                    continue
                
            # STEP5: 공통 WeeklyTrend 결과 저장
            if not self.env.bool('DEBUG', False):
                self.update_weekly_trend_result()
            
            logger.info(
                f"Newsletter batch process completed."
                f"Processed: {total_processed}, Failed: {total_failed}"
            )
            
        except Exception as e:
            logger.error(f"Newsletter batch process failed: {e}")
            raise e from e


if __name__ == "__main__":
    WeeklyNewsletterBatch().run()