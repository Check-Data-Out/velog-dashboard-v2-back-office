"""
[25.07.01] 주간 사용자 분석 배치 (작성자: 이지현)
- 실행은 아래와 같은 커멘드 활용
- poetry run python ./insight/tasks/user_weekly_trend_analysis.py
"""

import asyncio
import logging
from datetime import timedelta

import aiohttp
import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import OuterRef, Subquery
from weekly_llm_analyzer import analyze_user_posts

from insight.models import UserWeeklyTrend
from posts.models import Post, PostDailyStatistics
from scraping.velog.client import VelogClient
from users.models import User
from utils.utils import get_previous_week_range

logger = logging.getLogger("scraping")


async def run_weekly_user_trend_analysis(user, velog_client, week_start, week_end):
    """각 사용자에 대한 주간 통계 데이터를 바탕으로 요약 및 분석"""
    user_id = user["id"]
    try:
        # 1. 게시글 목록 + 최신 통계 정보 가져오기
        latest_stats_subquery = PostDailyStatistics.objects.filter(
            post=OuterRef("pk")
        ).order_by("-date")

        posts = await sync_to_async(list)(
            Post.objects.filter(user_id=user_id)
            .annotate(
                latest_view_count=Subquery(latest_stats_subquery.values("daily_view_count")[:1]),
                latest_like_count=Subquery(latest_stats_subquery.values("daily_like_count")[:1]),
            )
            .values("id", "title", "post_uuid", "latest_view_count", "latest_like_count")
        )

        if not posts:
            logger.info("[user_id=%s] No posts found. Skipping.", user_id)
            return None

        # 2. 단순 요약 문자열 생성
        simple_summary = (
            f"총 게시글 수: {len(posts)}, "
            f"총 조회수: {sum(p['latest_view_count'] or 0 for p in posts)}, "
            f"총 좋아요 수: {sum(p['latest_like_count'] or 0 for p in posts)}"
        )

        # 3. Velog 게시글 상세 조회
        full_contents = []
        post_meta = []

        for p in posts:
            try:
                velog_post = await velog_client.get_post(str(p["post_uuid"]))
                if velog_post and velog_post.body:
                    full_contents.append(
                        {
                            "제목": p["title"],
                            "내용": velog_post.body,
                            "조회수": p["latest_view_count"] or 0,
                            "좋아요 수": p["latest_like_count"] or 0,
                        }
                    )
                    post_meta.append(
                        {
                            "title": p["title"],
                            "username": velog_post.user.username if velog_post.user else "",
                            "thumbnail": velog_post.thumbnail or "",
                            "slug": velog_post.url_slug or "",
                        }
                    )
            except Exception as err:
                logger.warning("[user_id=%s] Failed to fetch Velog post : %s", user_id, err)
                continue

        # 4. LLM 분석 (게시글 단위로 개별 분석 처리)
        detailed_insight = []

        for i, post in enumerate(full_contents):
            try:
                result = analyze_user_posts([post], settings.OPENAI_API_KEY)
                result_item = result[0] if result else {}

                meta = post_meta[i] if i < len(post_meta) else {}
                detailed_insight.append(
                    {
                        "summary": result_item.get("summary", ""),
                        "key_points": result_item.get("key_points", []),
                        "username": meta.get("username", ""),
                        "thumbnail": meta.get("thumbnail", ""),
                        "slug": meta.get("slug", ""),
                    }
                )
            except Exception as err:
                logger.warning(
                    "[user_id=%s] LLM analysis failed for post index %d: %s", user_id, i, err
                )
                continue

        # 5. 인사이트 저장 포맷
        insight = {
            "trending_summary": simple_summary,
            "trend_analysis": detailed_insight,
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
                logger.warning("[user_id=%s] Failed to prepare Velog client : %s", user["id"], e)

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
