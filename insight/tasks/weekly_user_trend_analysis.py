"""
[25.07.01] 주간 사용자 분석 배치 (작성자: 이지현)
- 실행은 아래와 같은 커멘드 활용
- poetry run python ./insight/tasks/weekly_user_trend_analysis.py

[25.07.12] 주간 사용자 분석 배치 (작성자: 정현우)
- class based 와 전체적인 구조 리펙토링
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings

from insight.models import TrendingItem, UserWeeklyTrend
from posts.models import Post, PostDailyStatistics
from users.models import User

from .base_analysis import AnalysisContext, BaseBatchAnalyzer
from .weekly_llm_analyzer import analyze_user_posts


@dataclass
class UserPostData:
    """사용자 게시글 데이터"""

    user_id: int
    username: str
    post: Post
    body: str
    view_diff: int
    like_diff: int

    def to_llm_format(self) -> dict[str, Any]:
        """LLM 분석용 포맷으로 변환"""
        return {
            "제목": self.post.title,
            "내용": self.body,
            "조회수": self.view_diff,
            "좋아요 수": self.like_diff,
        }


@dataclass
class UserWeeklyResult:
    """사용자 주간 분석 결과"""

    user_id: int
    trending_items: list[TrendingItem]
    simple_summary: str


class UserWeeklyAnalyzer(BaseBatchAnalyzer[UserWeeklyResult]):
    """사용자별 주간 분석기"""

    async def _fetch_data(
        self, context: AnalysisContext
    ) -> list[UserPostData]:
        """사용자별 게시글 데이터 수집"""
        try:
            # 활성 사용자 목록 조회
            users = await sync_to_async(list)(
                User.objects.filter(email__isnull=False, is_active=True)
                .exclude(email="")
                .values("id", "username", "access_token", "refresh_token")
            )

            all_user_posts = []

            for user in users:
                user_id = user["id"]
                try:
                    user_posts = await self._fetch_user_posts(user_id, context)
                    all_user_posts.extend(user_posts)
                except Exception as e:
                    self.logger.warning(
                        "Failed to fetch posts for user %s: %s", user_id, e
                    )
                    continue

            self.logger.info("Fetched posts for %d users", len(users))
            return all_user_posts

        except Exception as e:
            self.logger.error("Failed to fetch user data: %s", e)
            raise

    async def _fetch_user_posts(
        self, user_id: int, context: AnalysisContext
    ) -> list[UserPostData]:
        """특정 사용자의 게시글 데이터 수집"""
        # 해당 주간의 게시글 조회
        posts = await sync_to_async(list)(
            Post.objects.filter(
                user_id=user_id,
                released_at__range=(context.week_start, context.week_end),
                is_active=True,
            )
            .select_related("user")
            .values("id", "title", "post_uuid", "user__username")
        )

        if not posts:
            return []

        # 통계 데이터 조회
        post_ids = [p["id"] for p in posts]
        prev_day = context.week_start - timedelta(days=1)

        stats_qs = await sync_to_async(list)(
            PostDailyStatistics.objects.filter(
                post_id__in=post_ids,
                date__in=[prev_day.date(), context.week_end.date()],
            ).values("post_id", "date", "daily_view_count", "daily_like_count")
        )

        # 통계 데이터 매핑
        stats_by_post = defaultdict(dict)
        for stat in stats_qs:
            stats_by_post[stat["post_id"]][stat["date"]] = {
                "view": stat["daily_view_count"],
                "like": stat["daily_like_count"],
            }

        # Velog 게시글 본문 조회 및 UserPostData 생성
        user_posts = []
        for post_data in posts:
            post_id = post_data["id"]
            post_uuid = post_data["post_uuid"]
            username = post_data["user__username"]

            # 조회수/좋아요 증가분 계산
            stat_map = stats_by_post.get(post_id, {})
            today_stats = stat_map.get(context.week_end.date(), {})
            prev_stats = stat_map.get(prev_day.date(), {})

            view_diff = (today_stats.get("view", 0)) - (
                prev_stats.get("view", 0)
            )
            like_diff = (today_stats.get("like", 0)) - (
                prev_stats.get("like", 0)
            )

            try:
                # Velog에서 게시글 본문 조회
                velog_post = await context.velog_client.get_post(
                    str(post_uuid)
                )
                body = (
                    velog_post.body if velog_post and velog_post.body else ""
                )

                # Post 객체 생성 (simplified)
                post_obj = Post(post_uuid=post_uuid, title=post_data["title"])

                user_post = UserPostData(
                    user_id=user_id,
                    username=username,
                    post=post_obj,
                    body=body,
                    view_diff=view_diff,
                    like_diff=like_diff,
                )
                user_posts.append(user_post)

            except Exception as e:
                self.logger.warning(
                    "Failed to fetch Velog post %s for user %s: %s",
                    post_uuid,
                    user_id,
                    e,
                )
                continue

        return user_posts

    async def _analyze_data(
        self, raw_data: list[UserPostData], context: AnalysisContext
    ) -> list[UserWeeklyResult]:
        """사용자별 데이터 분석"""
        # 사용자별로 데이터 그룹핑
        user_posts_map = defaultdict(list)
        for user_post in raw_data:
            user_posts_map[user_post.user_id].append(user_post)

        results = []

        for user_id, user_posts in user_posts_map.items():
            try:
                result = await self._analyze_user_posts(user_id, user_posts)
                if result:
                    results.append(result)
            except Exception as e:
                self.logger.error(
                    "Failed to analyze posts for user %s: %s", user_id, e
                )
                continue

        return results

    async def _analyze_user_posts(
        self, user_id: int, user_posts: list[UserPostData]
    ) -> UserWeeklyResult:
        """특정 사용자의 게시글 분석"""
        if not user_posts:
            return None

        # 간단한 통계 요약
        total_posts = len(user_posts)
        total_views = sum(post.view_diff for post in user_posts)
        total_likes = sum(post.like_diff for post in user_posts)

        simple_summary = f"총 게시글 수: {total_posts}, 총 조회수: {total_views}, 총 좋아요 수: {total_likes}"

        # LLM 분석
        trending_items = []

        for user_post in user_posts:
            try:
                # 각 게시글별로 개별 분석
                llm_input = [user_post.to_llm_format()]
                llm_result = analyze_user_posts(
                    llm_input, settings.OPENAI_API_KEY
                )

                trending_summary = llm_result.get("trending_summary", [])
                if trending_summary and isinstance(trending_summary, list):
                    first_summary = trending_summary[0]

                    trending_item = TrendingItem(
                        title=user_post.post.title,
                        summary=first_summary.get("summary", "[요약 실패]"),
                        key_points=first_summary.get("key_points", []),
                        username=user_post.username,
                        thumbnail="",  # UserPostData에서는 썸네일 정보 없음
                        slug="",  # UserPostData에서는 슬러그 정보 없음
                    )
                    trending_items.append(trending_item)

            except Exception as e:
                self.logger.warning(
                    "LLM analysis failed for user %s post %s: %s",
                    user_id,
                    user_post.post.post_uuid,
                    e,
                )
                # 분석 실패 시 기본 아이템 추가
                trending_item = TrendingItem(
                    title=user_post.post.title,
                    summary="[분석 실패]",
                    key_points=[],
                    username=user_post.username,
                    thumbnail="",
                    slug="",
                )
                trending_items.append(trending_item)

        return UserWeeklyResult(
            user_id=user_id,
            trending_items=trending_items,
            simple_summary=simple_summary,
        )

    async def _save_results(
        self, results: list[UserWeeklyResult], context: AnalysisContext
    ) -> None:
        """결과를 데이터베이스에 저장"""
        for result in results:
            try:
                insight_data = {
                    "trending_summary": [
                        item.to_dict() for item in result.trending_items
                    ],
                    "trend_analysis": {"summary": result.simple_summary},
                }

                await sync_to_async(UserWeeklyTrend.objects.update_or_create)(
                    user_id=result.user_id,
                    week_start_date=context.week_start.date(),
                    week_end_date=context.week_end.date(),
                    defaults={
                        "insight": insight_data,
                        "is_processed": True,
                        "processed_at": context.week_start,
                    },
                )

            except Exception as e:
                self.logger.error(
                    "Failed to save UserWeeklyTrend for user %s: %s",
                    result.user_id,
                    e,
                )
                continue

        self.logger.info("Saved %d user weekly trends", len(results))


async def main():
    """메인 실행 함수"""
    analyzer = UserWeeklyAnalyzer()
    result = await analyzer.run()

    if result.success:
        print(f"✅ 사용자 주간 분석 완료: {result.metadata}")
    else:
        print(f"❌ 사용자 주간 분석 실패: {result.error}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
