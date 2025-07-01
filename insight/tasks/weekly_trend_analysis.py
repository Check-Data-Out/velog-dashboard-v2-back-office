import asyncio
import logging

import aiohttp
import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings
from weekly_llm_analyzer import analyze_trending_posts

from insight.models import WeeklyTrend
from scraping.velog.client import VelogClient
from utils.utils import get_previous_week_range

logger = logging.getLogger("scraping")


async def retry_fetch_trending_posts(client, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await client.get_trending_posts(limit=10)
        except Exception as e:
            logger.warning("Trending posts fetch failed (attempt %d): %s", attempt + 1, e)
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)
    return []


async def retry_fetch_post_detail(client, post_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await client.get_post(post_id)
        except Exception as e:
            logger.warning("Failed to fetch post detail (id=%s, attempt %d): %s", post_id, attempt + 1, e)
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)
    return None


async def retry_analyze_trending_posts(payload, api_key, max_retries=3):
    for attempt in range(max_retries):
        try:
            return analyze_trending_posts(payload, api_key)
        except Exception as e:
            logger.warning("[user_id=%s] LLM analysis failed (attempt %d): %s", attempt + 1)
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)
    return ""


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

            trending_posts = await retry_fetch_trending_posts(velog_client)
        except Exception as e:
            logger.exception("Velog client init or trending post fetch failed: %s", e)
            return

        if not trending_posts:
            logger.info("No trending posts found for the past week")
            return

        payload = []
        for post in trending_posts:
            detail = await retry_fetch_post_detail(velog_client, post.id)
            body = detail.body if detail and detail.body else ""
            payload.append(
                {
                    "제목": post.title,
                    "내용": body,
                    "조회수": post.views,
                    "좋아요 수": post.likes,
                    "사용자 이름": post.user.username,
                    "게시글 썸네일": post.thumbnail,
                }
            )

    insight_data = await retry_analyze_trending_posts(payload, settings.OPENAI_API_KEY)

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


if __name__ == "__main__":
    asyncio.run(run_weekly_trend_analysis())
