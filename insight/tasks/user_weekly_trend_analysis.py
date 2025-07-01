import logging
import asyncio
from collections import defaultdict

import aiohttp
import setup_django  # noqa
from django.conf import settings
from django.db.models import Sum
from asgiref.sync import sync_to_async

from insight.models import UserWeeklyTrend
from posts.models import PostDailyStatistics
from users.models import User
from scraping.velog.client import VelogClient
from utils.utils import get_previous_week_range
from weekly_llm_analyzer import analyze_user_posts

logger = logging.getLogger("scraping")


async def fetch_post_body(p, velog_client, user_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            velog_post = await velog_client.get_post(p["post_uuid"])
            if velog_post and velog_post.body:
                return {
                    "제목": p["title"],
                    "내용": velog_post.body,
                    "조회수": p["views"],
                    "좋아요 수": p["likes"],
                    "사용자 이름": velog_post.user.username,
                    "게시글 썸네일": velog_post.thumbnail,
                }
            break  # 본문 없으면 굳이 재시도 안 함
        except Exception as err:
            logger.warning(
                "[user_id=%s] Failed to fetch Velog post (attempt %d): %s",
                user_id,
                attempt + 1,
                err,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (2**attempt))  # 지수 백오프
    return None


async def retry_analyze_user_posts(contents, api_key, user_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            return analyze_user_posts(contents, api_key)
        except Exception as err:
            logger.warning(
                "[user_id=%s] LLM analysis failed (attempt %d): %s", user_id, attempt + 1, err
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (2**attempt))
    return ""


async def run_weekly_user_trend_analysis(
    user: dict, velog_client: VelogClient, week_start, week_end
):
    user_id = user["id"]
    try:
        stats = await sync_to_async(list)(
            PostDailyStatistics.objects.filter(
                post__user_id=user_id, date__range=(week_start, week_end)
            ).select_related("post")
        )

        if not stats:
            logger.info("[user_id=%s] No statistics found. Skipping.", user_id)
            return None

        post_map = defaultdict(
            lambda: {"title": "", "views": 0, "likes": 0, "post_uuid": ""}
        )
        for stat in stats:
            post = stat.post
            post_map[post.id]["title"] = post.title
            post_map[post.id]["views"] += stat.daily_view_count
            post_map[post.id]["likes"] += stat.daily_like_count
            post_map[post.id]["post_uuid"] = str(post.post_uuid)

        payload_simple = [
            {"제목": p["title"], "조회수": p["views"], "좋아요 수": p["likes"]}
            for p in post_map.values()
        ]
        simple_summary = (
            f"총 게시글 수: {len(payload_simple)}, "
            f"총 조회수: {sum(p['조회수'] for p in payload_simple)}, "
            f"총 좋아요 수: {sum(p['좋아요 수'] for p in payload_simple)}"
        )

        tasks = [fetch_post_body(p, velog_client, user_id) for p in post_map.values()]
        full_contents = [res for res in await asyncio.gather(*tasks) if res]

        llm_result = ""
        if full_contents:
            llm_result = await retry_analyze_user_posts(
                full_contents, settings.OPENAI_API_KEY, user_id
            )

        insight = f"[요약 분석]\n{simple_summary}\n\n[LLM 분석]\n{llm_result}"

        return UserWeeklyTrend(
            user_id=user_id,
            week_start_date=week_start,
            week_end_date=week_end,
            insight=insight,
        )

    except Exception as e:
        logger.exception("[user_id=%s] Unexpected error: %s", user_id, e)
        return None


async def run_all_users():
    logger.info("User weekly trend analysis started")
    week_start, week_end = get_previous_week_range()

    users = await sync_to_async(list)(
        User.objects.filter(email__isnull=False)
        .exclude(email="")
        .values("id", "username", "access_token", "refresh_token")
    )

    results = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for user in users:
            try:
                velog_client = VelogClient.get_client(
                    session, user["access_token"], user["refresh_token"]
                )
                task = run_weekly_user_trend_analysis(
                    user, velog_client, week_start, week_end
                )
                tasks.append(task)
            except Exception as e:
                logger.warning("[user_id=%s] Failed to create Velog client: %s", user["id"], e)

        trends = await asyncio.gather(*tasks, return_exceptions=True)
        results = [t for t in trends if isinstance(t, UserWeeklyTrend)]

    for trend in results:
        try:
            await sync_to_async(UserWeeklyTrend.objects.update_or_create)(
                user_id=trend.user_id,
                week_start_date=trend.week_start_date,
                week_end_date=trend.week_end_date,
                defaults={"insight": trend.insight},
            )
        except Exception as e:
            logger.warning("[user_id=%s] Failed to save trend: %s", trend.user_id, e)


if __name__ == "__main__":
    asyncio.run(run_all_users())
