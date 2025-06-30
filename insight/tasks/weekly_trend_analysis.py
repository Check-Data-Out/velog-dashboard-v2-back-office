import logging
import asyncio
import aiohttp
from datetime import timedelta, datetime

from django.utils import timezone
from django.conf import settings
from asgiref.sync import sync_to_async

import setup_django  # noqa
from insight.models import WeeklyTrend
from scraping.velog.client import VelogClient
from weekly_llm_analyzer import analyze_trending_posts
from utils.utils import get_local_now

logger = logging.getLogger("scraping")


async def run_weekly_trend_analysis():
    """주간 트렌드 분석 배치 실행"""
    logger.info("Weekly trend analysis batch started")

    week_start, week_end = get_previous_week_range()

    async with aiohttp.ClientSession() as session:
        try:
            velog_client = VelogClient.get_client(
                session=session,
                access_token="dummy_access_token",
                refresh_token="dummy_refresh_token",
            )
            trending_posts = await velog_client.get_trending_posts(limit=10)
        except Exception as e:
            logger.exception("Failed to fetch trending posts from Velog API : %s", e)
            return

        if not trending_posts:
            logger.info("No trending posts found for the past week")
            return

        payload = []
        for post in trending_posts:
            try:
                detail = await velog_client.get_post(post.id)
                body = detail.body if detail and detail.body else ""
            except Exception as e:
                logger.warning("Failed to fetch post detail (id=%s) : %s", post.id, e)
                body = ""

            payload.append(
                {
                    "제목": post.title,
                    "내용": body,
                    "조회수": post.views,
                    "좋아요 수": post.likes,
                }
            )

    try:
        insight_data = analyze_trending_posts(payload, settings.OPENAI_API_KEY)
    except Exception as e:
        logger.exception("Failed to LLM analysis : %s", e)
        return

    try:
        await sync_to_async(WeeklyTrend.objects.update_or_create)(
            week_start_date=week_start,
            week_end_date=week_end,
            defaults={
                "insight": insight_data,
            },
        )
        logger.info("WeeklyTrend saved successfully")
    except Exception as e:
        logger.exception("Failed to save WeeklyTrend : %s", e)


def get_previous_week_range(today=None):
    """주간 날짜 계산"""
    today = today or get_local_now().date()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)

    week_start = timezone.make_aware(datetime.combine(last_monday, datetime.min.time()))
    week_end = timezone.make_aware(datetime.combine(last_sunday, datetime.max.time()))
    return week_start, week_end


if __name__ == "__main__":
    asyncio.run(run_weekly_trend_analysis())
