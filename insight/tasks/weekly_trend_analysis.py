"""
[25.07.01] 주간 트렌드 분석 배치 (작성자: 이지현)
- 실행은 아래와 같은 커멘드 활용
- poetry run python ./insight/tasks/weekly_trend_analysis.py
"""

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


async def run_weekly_trend_analysis():
    """Velog 트렌딩 게시글을 기반으로 주간 트렌드 분석"""
    logger.info("Weekly trend analysis batch started")

    # 1. 주간 시작/끝 날짜 계산
    week_start, week_end = get_previous_week_range()

    async with aiohttp.ClientSession() as session:
        try:
            # 2. Velog 트렌딩 게시글 조회
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
                # 3. Velog API 게시글 상세 조회
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
                    "사용자 이름": post.user.username,
                    "게시글 썸네일": post.thumbnail,
                }
            )

    try:
        # 4. LLM을 이용한 트렌드 분석
        insight_data = analyze_trending_posts(payload, settings.OPENAI_API_KEY)
    except Exception as e:
        logger.warning("LLM analysis failed: %s", e)
        insight_data = ""

    try:
        # 5. 결과 DB에 저장
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
