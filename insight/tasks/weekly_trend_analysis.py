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
from posts.models import Post
from insight.models import WeeklyTrend
from .weekly_llm_analyzer import analyze_trending_posts

logger = logging.getLogger("scraping")


def run_weekly_trend_analysis():
    logger.info("주간 트렌드 분석 배치 시작")
    week_start = timezone.now() - timedelta(weeks=1)
    week_end = timezone.now()

    try:
        posts = (
            Post.objects.filter(created_at__gte=week_start)
            .annotate(
                total_likes=Sum("daily_statistics__daily_like_count"),
                total_views=Sum("daily_statistics__daily_view_count")
            )
            .order_by("-total_likes")[:10]
        )
    except DatabaseError as e:
        logger.exception("게시글 조회 실패: %s", e)
        return

    if not posts:
        logger.info("지난주 인기 글이 없습니다.")
        return

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
        insight_data = analyze_trending_posts(payload)
    except Exception as e:
        logger.exception("LLM 분석 실패: %s", e)
        return

    try:
        WeeklyTrend.objects.create(
            week_start_date=week_start.date(),
            week_end_date=week_end.date(),
            insight=insight_data,
            is_processed=True,
            processed_at=timezone.now(),
        )
        logger.info("WeeklyTrend 저장 완료")
    except Exception as e:
        logger.exception("WeeklyTrend 저장 실패: %s", e)


if __name__ == "__main__":
    try:
        run_weekly_trend_analysis()
    except Exception:
        logger.exception("주간 트렌드 분석 중 알 수 없는 예외 발생")
