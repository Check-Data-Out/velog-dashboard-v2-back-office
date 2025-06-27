import logging
from datetime import timedelta
import asyncio

import aiohttp
from asgiref.sync import sync_to_async

from django.utils import timezone
from django.conf import settings

import setup_django  # noqa
from insight.models import WeeklyTrend
from scraping.velog.client import VelogClient
from weekly_llm_analyzer import analyze_trending_posts
from utils.utils import get_local_now

logger = logging.getLogger("scraping")

# TODO: 수정 필요
ACCESS_TOKEN = ""
REFRESH_TOKEN = ""


async def run_weekly_trend_analysis():
    logger.info("Weekly trend analysis batch started")

    week_start, week_end = get_previous_week_range()

    async with aiohttp.ClientSession() as session:
        try:
            velog_client = VelogClient.get_client(
                session=session,
                access_token=ACCESS_TOKEN,
                refresh_token=REFRESH_TOKEN,
            )
            trending_posts = await velog_client.get_trending_posts(limit=10)
        except Exception as e:
            logger.exception("Velog API failed: %s", e)
            return

        if not trending_posts:
            logger.info("No trending posts from the past week.")
            return

        payload = [
            {
                "제목": post.title,
                "내용": post.body or "",
                "조회수": post.views or 0,
                "좋아요 수": post.likes or 0,
            }
            for post in trending_posts
        ]

        try:
            insight_data = analyze_trending_posts(payload, settings.OPENAI_API_KEY)

        except Exception as e:
            logger.exception("LLM analysis failed: %s", e)
            return

        try:
            await sync_to_async(WeeklyTrend.objects.update_or_create)(
                week_start_date=week_start,
                week_end_date=week_end,
                insight=insight_data,
                is_processed=True,
                processed_at=timezone.now(),
            )
            logger.info("WeeklyTrend saved successfully")
        except Exception as e:
            logger.exception("Failed to save WeeklyTrend: %s", e)


def get_previous_week_range(today=None):
    today = today or get_local_now().date()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)

    return last_monday, last_sunday


if __name__ == "__main__":
    asyncio.run(run_weekly_trend_analysis())
