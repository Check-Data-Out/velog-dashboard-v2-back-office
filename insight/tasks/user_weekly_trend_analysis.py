import logging
from concurrent.futures import ThreadPoolExecutor

from django.db import DatabaseError
from django.db.models import Sum
from django.conf import settings

import setup_django  # noqa
from posts.models import Post
from insight.models import UserWeeklyTrend
from users.models import User
from weekly_llm_analyzer import analyze_user_posts
from utils.utils import get_previous_week_range

logger = logging.getLogger("scraping")


def process_user(user, week_start, week_end):
    """주간 사용자 트렌드 분석 배치 실행"""
    user_id = user["id"]
    try:
        try:
            posts = Post.objects.filter(
                user_id=user_id, created_at__gte=week_start
            ).annotate(
                total_likes=Sum("daily_statistics__daily_like_count"),
                total_views=Sum("daily_statistics__daily_view_count"),
            )
        except DatabaseError as db_err:
            logger.error("[user_id=%s] Failed to query posts : %s", user_id, db_err)
            return None

        if not posts.exists():
            logger.info("[user_id=%s] No posts in the selected period, skipping", user_id)
            return None

        payload = [
            {
                "제목": p.title,
                "조회수": p.total_views or 0,
                "좋아요 수": p.total_likes or 0,
            }
            for p in posts
        ]

        try:
            insight_data = analyze_user_posts(payload, settings.OPENAI_API_KEY)

        except Exception as llm_err:
            logger.error("[user_id=%s] Failed to analyze with OpenAI : %s", user_id, llm_err)
            return None

        try:
            trend = UserWeeklyTrend(
                user_id=user_id,
                week_start_date=week_start,
                week_end_date=week_end,
                insight=insight_data,
            )
            logger.info("[user_id=%s] Successfully created UserWeeklyTrend", user_id)
            return trend
        except Exception as save_err:
            logger.error(
                "[user_id=%s] Error occurred while creating UserWeeklyTrend : %s",
                user_id,
                save_err,
            )
            return None

    except Exception as e:
        logger.exception("[user_id=%s] Unexpected error occurred during processing : %s", user_id, e)
        return None


def run_multithreaded():
    """각 사용자별 UserWeeklyTrend 저장"""
    logger.info("User weekly trend analysis (threaded) started")

    week_start, week_end = get_previous_week_range()

    try:
        users = list(
            User.objects.filter(email__isnull=False)
            .exclude(email="")
            .values("id", "access_token", "refresh_token")
        )
    except Exception as user_fetch_err:
        logger.exception("Failed to fetch user list : %s", user_fetch_err)
        return

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(process_user, user, week_start, week_end) for user in users
        ]

        for future in futures:
            result = future.result()
            if result:
                results.append(result)

    for trend in results:
        try:
            UserWeeklyTrend.objects.update_or_create(
                user_id=trend.user_id,
                week_start_date=trend.week_start_date,
                week_end_date=trend.week_end_date,
                defaults={
                    "insight": trend.insight,
                },
            )
        except Exception as e:
            logger.warning(
                "[user_id=%s] Failed to update_or_create UserWeeklyTrend: %s",
                trend.user_id,
                e,
            )


if __name__ == "__main__":
    run_multithreaded()
