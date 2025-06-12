import os
import sys
import logging
from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum
from django.db import DatabaseError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)

from scraping import setup_django  # noqa
from users.models import User
from posts.models import Post
from insight.models import UserWeeklyTrend
from .weekly_llm_analyzer import analyze_user_posts

logger = logging.getLogger("scraping")


def run_user_weekly_trend_analysis():
    logger.info("사용자 주간 트렌드 분석 배치 시작")
    week_start = timezone.now() - timedelta(weeks=1)
    week_end = timezone.now()

    try:
        users = User.objects.all()
    except DatabaseError as e:
        logger.exception("사용자 목록 조회 실패: %s", e)
        return

    for user in users:
        try:
            posts = Post.objects.filter(
                user__username=user.username, created_at__gte=week_start
            ).annotate(
                total_likes=Sum("daily_statistics__daily_like_count"),
                total_views=Sum("daily_statistics__daily_view_count"),
            )

            if not posts.exists():
                logger.info("[%s] 최근 일주일 게시글 없음, 스킵", user.username)
                continue

            payload = [
                {
                    "제목": p.title,
                    "내용": p.slug or "",
                    "조회수": p.total_views or 0,
                    "좋아요 수": p.total_likes or 0,
                }
                for p in posts
            ]

            try:
                insight_data = analyze_user_posts(payload)
            except Exception as e:
                logger.exception("[%s] LLM 분석 실패: %s", user.username, e)
                continue

            try:
                UserWeeklyTrend.objects.create(
                    user=user,
                    week_start_date=week_start.date(),
                    week_end_date=week_end.date(),
                    insight=insight_data,
                    is_processed=True,
                    processed_at=timezone.now(),
                )
                logger.info("[%s] UserWeeklyTrend 저장 완료", user.username)
            except Exception as e:
                logger.exception("[%s] UserWeeklyTrend 저장 실패: %s", user.username, e)

        except Exception as e:
            logger.exception("[%s] 게시글 처리 중 예외 발생: %s", user.username, e)


if __name__ == "__main__":
    try:
        run_user_weekly_trend_analysis()
    except Exception:
        logger.exception("전체 사용자 주간 트렌드 분석 중 알 수 없는 예외 발생")
