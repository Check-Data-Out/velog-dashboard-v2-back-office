import logging
import asyncio
import aiohttp
from datetime import timedelta
from datetime import datetime

from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from asgiref.sync import sync_to_async

import setup_django  # noqa
from posts.models import Post
from insight.models import WeeklyTrend
from scraping.velog.client import VelogClient
from weekly_llm_analyzer import analyze_trending_posts
from utils.utils import get_local_now

logger = logging.getLogger("scraping")


async def run_weekly_trend_analysis():
    logger.info("주간 트렌드 분석 배치 시작")

    week_start, week_end = get_previous_week_range()

    try:
        posts = await sync_to_async(list)(
            Post.objects.filter(created_at__range=(week_start, week_end))
            .annotate(
                total_likes=Sum("daily_statistics__daily_like_count"),
                total_views=Sum("daily_statistics__daily_view_count"),
            )
            .order_by("-total_likes")[:10]
        )
    except Exception as e:
        logger.exception("게시글 조회 실패: %s", e)
        return

    if not posts:
        logger.info("지난주 인기 글이 없습니다.")
        return

    async with aiohttp.ClientSession() as session:
        velog_client = VelogClient.get_client(
            session=session,
            access_token="dummy_access_token",
            refresh_token="dummy_refresh_token",
        )

        payload = []
        for post in posts:
            try:
                detail = await velog_client.get_post(str(post.post_uuid))

                if isinstance(detail, dict):
                    body = detail.get("body", "")
                else:
                    body = getattr(detail, "body", "")
            except Exception as e:
                logger.warning("게시글 상세 조회 실패 (slug=%s): %s", post.slug, e)
                body = ""

            payload.append(
                {
                    "제목": post.title,
                    "내용": body,
                    "조회수": post.total_views or 0,
                    "좋아요 수": post.total_likes or 0,
                }
            )

    try:
        insight_data = analyze_trending_posts(payload, settings.OPENAI_API_KEY)
    except Exception as e:
        logger.exception("LLM 분석 실패: %s", e)
        return

    try:
        await sync_to_async(WeeklyTrend.objects.update_or_create)(
            week_start_date=week_start,
            week_end_date=week_end,
            defaults={
                "insight": insight_data,
                "is_processed": True,
                "processed_at": timezone.now(),
            },
        )
        logger.info("WeeklyTrend 저장 완료")
    except Exception as e:
        logger.exception("WeeklyTrend 저장 실패: %s", e)


def get_previous_week_range(today=None):
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
