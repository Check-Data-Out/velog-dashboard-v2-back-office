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
            # 2. 트렌딩 게시글 목록 조회
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

        full_contents = []
        post_meta = []

        # 3. 게시글 본문 조회 + 메타 저장
        for post in trending_posts:
            try:
                detail = await velog_client.get_post(post.id)
                body = detail.body if detail and detail.body else ""
            except Exception as e:
                logger.warning("Failed to fetch post detail (id=%s) : %s", post.id, e)
                body = ""

            full_contents.append(
                {
                    "제목": post.title,
                    "내용": body,
                    "조회수": post.views,
                    "좋아요 수": post.likes,
                }
            )
            post_meta.append(
                {
                    "title": post.title,
                    "username": post.user.username,
                    "thumbnail": post.thumbnail or "",
                    "slug": post.url_slug or "",
                }
            )

    try:
        # 4. LLM 분석
        llm_result = analyze_trending_posts(full_contents, settings.OPENAI_API_KEY)
        trending_summary_raw = llm_result.get("trending_summary", [])
        trend_analysis = llm_result.get("trend_analysis", {})
    except Exception as e:
        logger.exception("LLM analysis failed: %s", e)
        return

    # 5. 결과 포맷 가공
    trending_summary = []
    for i, item in enumerate(trending_summary_raw):
        meta = post_meta[i]
        trending_summary.append(
            {
                "title": meta["title"],
                "summary": item.get("summary", ""),
                "key_points": item.get("key_points", []),
                "username": meta["username"],
                "thumbnail": meta["thumbnail"],
                "slug": meta["slug"],
            }
        )

    # 6. 최종 insight 저장 포맷 구성
    insight = {
        "trending_summary": trending_summary,
        "trend_analysis": trend_analysis,
    }

    try:
        await sync_to_async(WeeklyTrend.objects.update_or_create)(
            week_start_date=week_start,
            week_end_date=week_end,
            defaults={"insight": insight},
        )
        logger.info("WeeklyTrend saved successfully")
    except Exception as e:
        logger.exception("Failed to save WeeklyTrend : %s", e)


if __name__ == "__main__":
    asyncio.run(run_weekly_trend_analysis())
