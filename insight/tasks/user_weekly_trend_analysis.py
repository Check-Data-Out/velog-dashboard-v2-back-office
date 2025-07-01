"""
[25.07.01] 주간 사용자 분석 배치 (작성자: 이지현)
- 실행은 아래와 같은 커멘드 활용
- poetry run python ./insight/tasks/user_weekly_trend_analysis.py
"""

import asyncio
import logging
from collections import defaultdict

import aiohttp
import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings
from weekly_llm_analyzer import analyze_user_posts

from insight.models import UserWeeklyTrend
from posts.models import PostDailyStatistics
from scraping.velog.client import VelogClient
from users.models import User
from utils.utils import get_previous_week_range

logger = logging.getLogger("scraping")


async def run_weekly_user_trend_analysis(
    user: dict, velog_client: VelogClient, week_start, week_end
):
    """각 사용자에 대한 주간 통계 데이터를 바탕으로 요약 및 분석"""
    user_id = user["id"]
    try:
        # 1. 주간 통계 정보 DB 조회
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

        # 2. 단순 요약 문자열 생성
        payload_simple = [
            {"제목": p["title"], "조회수": p["views"], "좋아요 수": p["likes"]}
            for p in post_map.values()
        ]
        simple_summary = (
            f"총 게시글 수: {len(payload_simple)}, "
            f"총 조회수: {sum(p['조회수'] for p in payload_simple)}, "
            f"총 좋아요 수: {sum(p['좋아요 수'] for p in payload_simple)}"
        )

        # 3. Velog API 게시글 상세 조회
        full_contents = []
        for p in post_map.values():
            try:
                velog_post = await velog_client.get_post(p["post_uuid"])
                if velog_post and velog_post.body:
                    full_contents.append(
                        {
                            "제목": p["title"],
                            "내용": velog_post.body,
                            "조회수": p["views"],
                            "좋아요 수": p["likes"],
                            "사용자 이름": velog_post.user.username,
                            "게시글 썸네일": velog_post.thumbnail,
                        }
                    )
            except Exception as err:
                logger.warning(
                    "[user_id=%s] Failed to fetch Velog post : %s", user_id, err
                )

        # 4. LLM을 이용한 사용자 분석
        try:
            llm_result = (
                analyze_user_posts(full_contents, settings.OPENAI_API_KEY)
                if full_contents
                else ""
            )
        except Exception as err:
            logger.warning("[user_id=%s] LLM analysis failed : %s", user_id, err)
            llm_result = ""

        # 5. 분석 결과 포맷 구성
        insight = f"[요약 분석]\n{simple_summary}\n\n[LLM 분석]\n{llm_result}"

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
    """주간 사용자 인사이트 생성 및 저장"""
    logger.info("User weekly trend analysis started")
    week_start, week_end = get_previous_week_range()

    # 1. 이메일이 존재하는 사용자 목록 조회
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
                # 2. 사용자별 VelogClient 생성 및 분석 task 등록
                velog_client = VelogClient.get_client(
                    session, user["access_token"], user["refresh_token"]
                )
                task = run_weekly_user_trend_analysis(
                    user, velog_client, week_start, week_end
                )
                tasks.append(task)
            except Exception as e:
                logger.warning(
                    "[user_id=%s] Failed to create Velog client : %s",
                    user["id"],
                    e,
                )

        trends = await asyncio.gather(*tasks, return_exceptions=True)
        results = [t for t in trends if isinstance(t, UserWeeklyTrend)]

    # 3. 분석 결과 저장
    for trend in results:
        try:
            await sync_to_async(UserWeeklyTrend.objects.update_or_create)(
                user_id=trend.user_id,
                week_start_date=trend.week_start_date,
                week_end_date=trend.week_end_date,
                defaults={"insight": trend.insight},
            )
        except Exception as e:
            logger.warning("[user_id=%s] Failed to save trend : %s", trend.user_id, e)


if __name__ == "__main__":
    asyncio.run(run_all_users())
