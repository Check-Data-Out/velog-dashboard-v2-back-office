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
from utils.utils import get_local_now

from modules.mail.schemas import AWSSESCredentials, EmailMessage
from modules.mail.ses.client import SESClient

logger = logging.getLogger(__name__)

class WeeklyNewsletterBatch:
    def __init__(self):
        self.env = environ.Env()
        self.chunk_size = 100
        self.max_retry_count = 3
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
            raise e from e

    def delete_old_maillogs(self) -> None:
        """
        7일 이전의 성공한 메일 발송 로그 삭제
        """
        NotiMailLog.objects.filter(
            created_at__lt=self.before_a_week,
            is_success=True,
        ).delete()
            
    def get_target_user_chunks(self) -> list[list[dict]]:
        """
        뉴스레터 발송 대상 유저 목록 조회
        """
        target_users = list(User.objects.filter(
            is_active=True,
            email__isnull=False,
        ).values('id', 'email', 'username').distinct())

        target_user_chunks = [target_users[i:i + self.chunk_size] for i in range(0, len(target_users), self.chunk_size)]
        return target_user_chunks

    def get_templated_weekly_trend(self) -> str:
        """
        공통 WeeklyTrend 조회 및 템플릿 적용
        """
        weekly_trend = WeeklyTrend.objects.filter(
            week_end_date__gte=self.before_a_week,
            is_processed=False,
        ).values('id', 'insight', 'week_start_date', 'week_end_date').first()

        if not weekly_trend:
            raise Exception("WeeklyTrend 데이터가 없습니다.")
        
        # 뉴스레터 정보 저장
        self.weekly_info = {
            'newletter_order': weekly_trend['id'],
            's_date': weekly_trend['week_start_date'],
            'e_date': weekly_trend['week_end_date'],
        }
    
        weekly_trend_html = render_to_string('insights/weekly_trend.html', {'insight': weekly_trend['insight']})

        return weekly_trend_html
    
    def get_user_weekly_stats(self, user_id: int) -> dict:
        """
        유저 주간 통계 조회
        """
        user_weekly_stats = PostDailyStatistics.objects.filter(
            post__user_id=user_id,
            date__gte=self.before_a_week,
        ).aggregate(
            posts=Count('post', distinct=True), 
            views=Sum('daily_view_count'), 
            likes=Sum('daily_like_count')
        )
        
        return {
            'posts': user_weekly_stats['posts'] or 0,
            'views': user_weekly_stats['views'] or 0,
            'likes': user_weekly_stats['likes'] or 0
        }

    def get_user_weekly_trends(self, user_chunk: list[dict]) -> dict[int, UserWeeklyTrend]:
        """
        뉴스레터 발송 대상 유저 목록에 대한 UserWeeklyTrend 조회
        """
        user_weekly_trends = UserWeeklyTrend.objects.filter(
            week_end_date__gte=self.before_a_week,
            user_id__in=[user['id'] for user in user_chunk],
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
        
        return user_weekly_trends_dict
    
    def get_expired_token_users(self, user_chunk: list[dict]) -> set[int]:
        """
        토큰 만료된 유저 ID 목록 조회
        """
        yesterday = timezone.now() - timedelta(days=1)
        user_ids = [user['id'] for user in user_chunk]
        
        active_user_ids = PostDailyStatistics.objects.filter(
            post__user_id__in=user_ids,
            date__gte=yesterday,
        ).values_list('post__user_id', flat=True).distinct()
        
        expired_user_ids = set(user_ids) - set(active_user_ids)
        return expired_user_ids

    def build_email_messages(self, user_chunk: list[dict], weekly_trend_html: str) -> list[EmailMessage]:
        """
        뉴스레터 템플릿 생성 및 target_user_chunk와 매핑된 메일 메시지 생성
        """
        user_weekly_trends_dict = self.get_user_weekly_trends(user_chunk)
        expired_token_user_ids = self.get_expired_token_users(user_chunk)

        email_messages = []
        for user in user_chunk:
            user_weekly_trend = user_weekly_trends_dict.get(user['id'])
            user_weekly_trend_html = None

            if user_weekly_trend:
                user_weekly_stats = self.get_user_weekly_stats(user['id'])
                
                user_weekly_trend_html = render_to_string('insights/user_weekly_trend.html', {
                    'insight': user_weekly_trend.insight, 
                    'user': user,
                    'user_weekly_stats': user_weekly_stats
                })
            
            is_expired = user['id'] in expired_token_user_ids
            
            html_body = render_to_string('insights/index.html', {
                'weekly_trend_html': weekly_trend_html, 
                'user_weekly_trend_html': user_weekly_trend_html, 
                's_date': self.weekly_info['s_date'], 
                'e_date': self.weekly_info['e_date'], 
                'is_expired_token_user': is_expired
            })
            text_body = html2text.HTML2Text().handle(html_body)
            
            email_message = EmailMessage(
                to=[user['email']],
                from_email=self.env('DEFAULT_FROM_EMAIL'),
                subject=f"벨로그 대시보드 주간 뉴스레터 #{self.weekly_info['newletter_order']}",
                text_body=text_body,
                html_body=html_body,
            )
            email_messages.append(email_message)
        
        return email_messages
    
    def send_newsletter_for_3_times(self, email_messages: list[EmailMessage]) -> list[str]:
        """
        뉴스레터 발송
        """
        failed_list = []
        for email_message in email_messages:
            failed_count = 0
            while True:
                try:
                    self.ses_client.send_email(email_message)
                    break
                except Exception as e:
                    failed_count += 1
                    if failed_count == self.max_retry_count:
                        failed_list.append(email_message.to[0])
                        break
                    continue

        return failed_list
    
    def update_weekly_trend_result(self) -> None:
        """
        뉴스레터 발송 결과 공통부분(WeeklyTrend) 저장
        """
        WeeklyTrend.objects.filter(
            id=self.weekly_info['newletter_order'],
        ).update(
            is_processed=True,
            processed_at=timezone.now(),
        )

    def update_user_weekly_trend_result(self, user_chunk: list[dict], failed_list: list[str]) -> None:
        """
        뉴스레터 발송 결과 개인화된 부분(UserWeeklyTrend) 저장
        """
        success_user_ids = [user['id'] for user in user_chunk if user['email'] not in failed_list]

        UserWeeklyTrend.objects.filter(
            user_id__in=success_user_ids,
        ).update(
            is_processed=True,
            processed_at=timezone.now(),
        )

    def run(self):
        # 1. 7일 이전의 성공한 메일 발송 로그 삭제
        self.delete_old_maillogs()

        # 2. 뉴스레터 발송 대상 유저 목록 조회
        target_user_chunks = self.get_target_user_chunks()

        # 3. 공통 WeeklyTrend 조회
        weekly_trend_html = self.get_templated_weekly_trend()

        # 4. 청크별로 뉴스레터 발송 및 결과 저장
        for user_chunk in target_user_chunks:
            email_messages = self.build_email_messages(user_chunk, weekly_trend_html)
            if self.env('DEBUG'):
                print(email_messages[0].text_body)
                continue
            else:
                failed_list = self.send_newsletter_for_3_times(email_messages)
                self.update_user_weekly_trend_result(user_chunk, failed_list)
                
        # 5. 공통 WeeklyTrend 결과 저장
        if self.env('DEBUG'):
            pass
        else:
            self.update_weekly_trend_result()

if __name__ == "__main__":
    WeeklyNewsletterBatch().run()