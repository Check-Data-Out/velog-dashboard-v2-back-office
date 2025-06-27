import logging
import time
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from django.db import DatabaseError
from django.db.models import Sum
from django.conf import settings

import setup_django  # noqa
from posts.models import Post
from insight.models import UserWeeklyTrend
from users.models import User
from weekly_llm_analyzer import analyze_user_posts
from utils.utils import get_local_now

logger = logging.getLogger("scraping")


def process_user(user, week_start, week_end):
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
                week_start_date=week_start.date(),
                week_end_date=week_end.date(),
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
    logger.info("User weekly trend analysis (threaded) started")
    week_start = get_local_now() - timedelta(weeks=1)
    week_end = get_local_now()

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

    if results:
        UserWeeklyTrend.objects.bulk_update_or_create(results)
        logger.info("All UserWeeklyTrends saved using bulk_update_or_create")


if __name__ == "__main__":
    start = time.time()
    try:
        run_multithreaded()
    except Exception:
        logger.exception("Unexpected error occurred during user weekly trend analysis")
    finally:
        end = time.time()
        duration = end - start
        logger.info(f"Finished in {duration:.2f} seconds")
