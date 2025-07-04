import asyncio
import logging
from datetime import timedelta

import aiohttp
import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Sum
from weekly_llm_analyzer import analyze_user_posts

from insight.models import UserWeeklyTrend
from posts.models import PostDailyStatistics
from scraping.velog.client import VelogClient
from users.models import User
from utils.utils import get_previous_week_range

logger = logging.getLogger("scraping")


async def run_weekly_user_trend_analysis(user, velog_client, week_start, week_end):
    user_id = user["id"]
    try:
        # 1. 주간 통계 정보 집계(DB에서 직접 집계)
        stats = await sync_to_async(list)(
            PostDailyStatistics.objects.filter(
                post__user_id=user_id,
                post__created_at__range=(week_start, week_end),
            )
            .values("post__id", "post__title", "post__post_uuid")
            .annotate(
                total_views=Sum("daily_view_count"),
                total_likes=Sum("daily_like_count"),
            )
        )

        if not stats:
            logger.info("[user_id=%s] No statistics found. Skipping.", user_id)
            return None

        # 2. 단순 요약 문자열 생성
        simple_summary = (
            f"총 게시글 수: {len(stats)}, "
            f"총 조회수: {sum(p['total_views'] for p in stats)}, "
            f"총 좋아요 수: {sum(p['total_likes'] for p in stats)}"
        )

        # 3. Velog 게시글 상세 조회
        full_contents = []
        post_meta = []

        for p in stats:
            try:
                velog_post = await velog_client.get_post(str(p["post__post_uuid"]))
                if velog_post and velog_post.body:
                    full_contents.append(
                        {
                            "제목": p["post__title"],
                            "내용": velog_post.body,
                            "조회수": p["total_views"],
                            "좋아요 수": p["total_likes"],
                        }
                    )
                    post_meta.append(
                        {
                            "title": p["post__title"],
                            "username": (
                                velog_post.user.username if velog_post.user else ""
                            ),
                            "thumbnail": velog_post.thumbnail or "",
                            "slug": velog_post.url_slug or "",
                        }
                    )
            except Exception as err:
                logger.warning(
                    "[user_id=%s] Failed to fetch Velog post : %s", user_id, err
                )
                continue

        # 4. LLM 분석
        try:
            llm_result = (
                analyze_user_posts(full_contents, settings.OPENAI_API_KEY)
                if full_contents
                else []
            )
        except Exception as err:
            logger.exception("[user_id=%s] LLM analysis failed : %s", user_id, err)
            llm_result = []

        detailed_insight = []
        for i, item in enumerate(llm_result):
            meta = post_meta[i]
            detailed_insight.append(
                {
                    "title": meta["title"],
                    "summary": item.get("summary", ""),
                    "key_points": item.get("key_points", []),
                    "username": meta["username"],
                    "thumbnail": meta["thumbnail"],
                    "slug": meta["slug"],
                }
            )

        # 5. 인사이트 저장 포맷
        insight = {
            "summary": simple_summary,
            "llm_analysis": detailed_insight,
        }

        return UserWeeklyTrend(
            user_id=user_id,
            week_start_date=week_start,
            week_end_date=week_end,
            insight=insight,
        )

    except Exception as e:
        logger.exception("[user_id=%s] Unexpected error : %s", user_id, e)
        return None


async def run_all_users():
    logger.info("User weekly trend analysis started")
    week_start, week_end = get_previous_week_range()

    # 1. 사용자 목록 조회
    users = await sync_to_async(list)(
        User.objects.filter(email__isnull=False)
        .exclude(email="")
        .values("id", "username", "access_token", "refresh_token")
    )

    async with aiohttp.ClientSession() as session:
        # 2. VelogClient 싱글톤 생성
        velog_client = VelogClient.get_client(
            session=session,
            access_token="dummy_access_token",
            refresh_token="dummy_refresh_token",
        )

        tasks = []
        for user in users:
            try:
                # 3. 분석 task 등록
                tasks.append(
                    run_weekly_user_trend_analysis(
                        user, velog_client, week_start, week_end
                    )
                )
            except Exception as e:
                logger.warning(
                    "[user_id=%s] Failed to prepare Velog client : %s", user["id"], e
                )

        # 4. 비동기 병렬 처리
        trends = await asyncio.gather(*tasks, return_exceptions=True)
        results = [t for t in trends if isinstance(t, UserWeeklyTrend)]

    # 5. DB 저장
    for trend in results:
        try:
            await sync_to_async(UserWeeklyTrend.objects.update_or_create)(
                user_id=trend.user_id,
                week_start_date=trend.week_start_date,
                week_end_date=trend.week_end_date,
                defaults={"insight": trend.insight},
            )
        except Exception as e:
            logger.exception("[user_id=%s] Failed to save trend : %s", trend.user_id, e)


if __name__ == "__main__":
    asyncio.run(run_all_users())
