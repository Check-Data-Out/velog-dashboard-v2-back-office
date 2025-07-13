"""
[25.07.01] 주간 사용자 분석 배치 (작성자: 이지현)
- 실행은 아래와 같은 커멘드 활용
- poetry run python ./insight/tasks/weekly_user_trend_analysis.py

[25.07.13] 주간 사용자 분석 배치 (작성자: 정현우)
- class based 와 전체적인 구조 리펙토링
- WeeklyUserTrendInsight 스키마 적용
- WeeklyUserStats, WeeklyUserReminder 로직 추가
- 토큰 만료 감지 로직 개선 (오늘자 통계 데이터 확인)
- 토큰 유효한 모든 사용자 대상으로 무조건 전체 통계 분석 실행
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Q

from insight.models import (
    TrendAnalysis,
    TrendingItem,
    UserWeeklyTrend,
    WeeklyUserReminder,
    WeeklyUserStats,
    WeeklyUserTrendInsight,
)
from insight.tasks.base_analysis import AnalysisContext, BaseBatchAnalyzer
from insight.tasks.weekly_llm_analyzer import analyze_user_posts
from posts.models import Post, PostDailyStatistics
from scraping.velog.schemas import Post as VelogPost
from users.models import User


class TokenExpiredError(Exception):
    """토큰 만료 예외"""

    def __init__(self, user_id: int, message: str = "Token expired"):
        self.user_id = user_id
        self.message = message
        super().__init__(message)


@dataclass
class UserWeeklyData:
    """사용자 주간 데이터"""

    user_id: int
    username: str
    weekly_new_posts: list[VelogPost]  # 주간 새글 (LLM 분석용)
    weekly_total_stats: WeeklyUserStats  # 주간 전체 통계


class UserWeeklyAnalyzer(BaseBatchAnalyzer[dict]):
    """사용자별 주간 분석기"""

    def __init__(self):
        super().__init__()
        self.expired_token_users = set()
        self.successful_users = set()
        self.all_target_users = set()

    async def _check_user_token_validity(
        self, user_id: int, context: AnalysisContext
    ) -> bool:
        """토큰 유효성 확인 - 오늘자 통계 데이터로 판단"""
        today = context.week_end

        user_posts = await sync_to_async(list)(
            Post.objects.filter(user_id=user_id, is_active=True).values_list(
                "id", flat=True
            )
        )

        if not user_posts:
            return True

        today_stats_count = await sync_to_async(
            PostDailyStatistics.objects.filter(
                post_id__in=user_posts, date=today
            ).count
        )()

        if today_stats_count == 0:
            self.logger.warning(
                "User %s token expired - no today stats", user_id
            )
            return False

        return True

    async def _create_user_reminder(
        self, user_id: int, context: AnalysisContext
    ) -> WeeklyUserReminder | None:
        """글이 없는 사용자용 리마인더 생성"""
        last_post = await sync_to_async(
            Post.objects.filter(
                user_id=user_id, is_active=True, released_at__isnull=False
            )
            .order_by("-released_at")
            .first
        )()

        if not last_post:
            return None

        days_ago = (
            context.week_end.date() - last_post.released_at.date()
        ).days
        return WeeklyUserReminder(title=last_post.title, days_ago=days_ago)

    async def _calculate_user_weekly_total_stats(
        self, user_id: int, context: AnalysisContext
    ) -> WeeklyUserStats:
        """사용자의 주간 전체 통계 계산 (모든 게시글 대상)"""
        # 사용자의 모든 활성 게시글 조회
        all_posts = await sync_to_async(list)(
            Post.objects.filter(
                user_id=user_id,
                is_active=True,
            ).values_list("id", flat=True)
        )

        # 주간 새글 개수 조회
        new_posts_count = await sync_to_async(
            Post.objects.filter(
                user_id=user_id,
                released_at__range=(context.week_start, context.week_end),
                is_active=True,
            ).count
        )()

        if not all_posts:
            return WeeklyUserStats(
                posts=0, new_posts=new_posts_count, views=0, likes=0
            )

        # 주간 통계 데이터 조회 (주간 시작일과 종료일)
        stats_qs = await sync_to_async(list)(
            PostDailyStatistics.objects.filter(
                Q(post_id__in=all_posts)
                & Q(date__in=[context.week_start, context.week_end])
            ).values("post_id", "date", "daily_view_count", "daily_like_count")
        )

        # 통계 매핑
        stats_by_post = defaultdict(dict)
        for stat in stats_qs:
            stats_by_post[stat["post_id"]][stat["date"]] = {
                "view": stat["daily_view_count"],
                "like": stat["daily_like_count"],
            }

        # 전체 통계 계산
        total_views = 0
        total_likes = 0
        posts_with_stats = 0

        for post_id in all_posts:
            stat_map = stats_by_post.get(post_id, {})
            week_end_stats = stat_map.get(context.week_end, {})
            week_start_stats = stat_map.get(context.week_start, {})

            # 주간 증가분 계산
            if week_end_stats and week_start_stats:
                view_diff = week_end_stats.get(
                    "view", 0
                ) - week_start_stats.get("view", 0)
                like_diff = week_end_stats.get(
                    "like", 0
                ) - week_start_stats.get("like", 0)

                # 음수 방지 (토큰 만료 등의 이슈가 있을 수 있음)
                if view_diff >= 0 and like_diff >= 0:
                    total_views += view_diff
                    total_likes += like_diff
                    posts_with_stats += 1
            elif (
                week_end_stats
            ):  # 주간 시작일 데이터가 없는 경우 (새 게시글 등)
                total_views += week_end_stats.get("view", 0)
                total_likes += week_end_stats.get("like", 0)
                posts_with_stats += 1

        return WeeklyUserStats(
            posts=posts_with_stats,  # 통계가 있는 전체 게시글 수
            new_posts=new_posts_count,  # 주간 새 게시글 수
            views=total_views,  # 주간 조회수 증가분
            likes=total_likes,  # 주간 좋아요 증가분
        )

    def _convert_velog_posts_to_llm_format(
        self, posts: list[VelogPost]
    ) -> list[dict[str, Any]]:
        """VelogPost를 LLM 분석용 포맷으로 변환"""
        return [
            {
                "제목": post.title,
                "내용": post.body or "",
            }
            for post in posts
        ]

    def _convert_llm_to_trend_analysis(
        self, llm_trend_analysis: dict
    ) -> TrendAnalysis:
        """LLM의 trend_analysis를 TrendAnalysis 객체로 변환"""
        return TrendAnalysis(
            hot_keywords=llm_trend_analysis.get("hot_keywords", []),
            title_trends=llm_trend_analysis.get("title_trends", ""),
            content_trends=llm_trend_analysis.get("content_trends", ""),
            insights=llm_trend_analysis.get("insights", ""),
        )

    async def _analyze_user_posts_with_llm(
        self, user_posts: list[VelogPost], username: str
    ) -> tuple[list[TrendingItem], TrendAnalysis | None]:
        """사용자 게시글을 LLM으로 분석하여 올바른 객체로 변환"""
        if not user_posts:
            return [], None

        try:
            # LLM 분석 실행
            llm_input = self._convert_velog_posts_to_llm_format(user_posts)
            llm_result = analyze_user_posts(llm_input, settings.OPENAI_API_KEY)

            # trending_summary 변환
            trending_items = []
            llm_trending_summary = llm_result.get("trending_summary", [])

            for i, llm_item in enumerate(llm_trending_summary):
                if i < len(user_posts):  # 해당하는 user_post가 있는 경우
                    user_post = user_posts[i]
                    trending_item = TrendingItem(
                        title=llm_item.get("title", user_post.title),
                        summary=llm_item.get("summary", "[요약 실패]"),
                        key_points=llm_item.get("key_points", []),
                        username=username,
                        thumbnail=user_post.thumbnail or "",
                        slug=user_post.url_slug or "",
                    )
                    trending_items.append(trending_item)

            # trend_analysis 변환
            trend_analysis = None
            llm_trend_analysis = llm_result.get("trend_analysis", {})
            if llm_trend_analysis:
                trend_analysis = self._convert_llm_to_trend_analysis(
                    llm_trend_analysis
                )

            return trending_items, trend_analysis

        except Exception as e:
            self.logger.warning("LLM analysis failed: %s", e)
            # 실패 시 기본 아이템들 생성
            trending_items = []
            for user_post in user_posts:
                trending_items.append(
                    TrendingItem(
                        title=user_post.title,
                        summary="[분석 실패]",
                        key_points=[],
                        username=username,
                        thumbnail=user_post.thumbnail or "",
                        slug=user_post.url_slug or "",
                    )
                )
            return trending_items, None

    async def _fetch_data(
        self, context: AnalysisContext
    ) -> list[UserWeeklyData]:
        """사용자별 주간 데이터 수집"""
        try:
            # 대상 사용자 조회
            users = await sync_to_async(list)(
                User.objects.filter(
                    email__isnull=False,
                    is_active=True,
                    id__in=[244, 167, 77, 13, 8, 1],
                )
                .exclude(email="")
                .values("id", "username")
            )

            self.all_target_users = {user["id"] for user in users}
            user_weekly_data = []

            self.logger.info(
                "Starting data collection for %d users", len(users)
            )

            for user in users:
                user_id = user["id"]
                username = user["username"]

                try:
                    # 토큰 유효성 확인
                    if not await self._check_user_token_validity(
                        user_id, context
                    ):
                        self.expired_token_users.add(user_id)
                        continue

                    # 토큰이 유효하면 successful_users에 추가
                    self.successful_users.add(user_id)

                    # 1. 주간 새글 수집 (LLM 분석용)
                    weekly_new_posts = await self._fetch_user_weekly_new_posts(
                        user_id, context
                    )

                    # 2. 주간 전체 통계 계산
                    weekly_total_stats = (
                        await self._calculate_user_weekly_total_stats(
                            user_id, context
                        )
                    )

                    # UserWeeklyData 생성
                    user_data = UserWeeklyData(
                        user_id=user_id,
                        username=username,
                        weekly_new_posts=weekly_new_posts,
                        weekly_total_stats=weekly_total_stats,
                    )
                    user_weekly_data.append(user_data)

                    self.logger.debug(
                        "Collected data for user %s: %d new posts, stats(posts=%d, new_posts=%d, views=%d, likes=%d)",
                        user_id,
                        len(weekly_new_posts),
                        weekly_total_stats.posts,
                        weekly_total_stats.new_posts,
                        weekly_total_stats.views,
                        weekly_total_stats.likes,
                    )

                except TokenExpiredError:
                    self.expired_token_users.add(user_id)
                    self.logger.warning("Token expired for user %s", user_id)
                except Exception as e:
                    self.logger.warning(
                        "Failed to collect data for user %s: %s", user_id, e
                    )

            self.logger.info(
                "Data collection completed: %d successful, %d expired",
                len(self.successful_users),
                len(self.expired_token_users),
            )
            return user_weekly_data

        except Exception as e:
            self.logger.error("Failed to fetch user data: %s", e)
            raise

    async def _fetch_user_weekly_new_posts(
        self, user_id: int, context: AnalysisContext
    ) -> list[VelogPost]:
        """특정 사용자의 주간 새글 데이터 수집 (LLM 분석용)"""

        # 해당 주간 게시글 조회
        posts = await sync_to_async(list)(
            Post.objects.filter(
                user_id=user_id,
                released_at__range=(context.week_start, context.week_end),
                is_active=True,
            ).values("post_uuid")
        )

        if not posts:
            return []

        velog_posts = []
        for post_data in posts:
            try:
                # Velog 게시글 본문 조회
                velog_post = await context.velog_client.get_post(
                    str(post_data["post_uuid"])
                )
                if velog_post:
                    velog_posts.append(velog_post)

            except Exception as e:
                self.logger.warning(
                    "Failed to fetch Velog post %s: %s",
                    post_data["post_uuid"],
                    e,
                )

        return velog_posts

    async def _analyze_data(
        self, raw_data: list[UserWeeklyData], context: AnalysisContext
    ) -> list[dict]:
        """사용자별 데이터 분석"""

        results = []

        self.logger.info("Starting analysis for %d users", len(raw_data))

        for user_data in raw_data:
            try:
                insight = await self._analyze_user_data(user_data, context)

                results.append(
                    {"user_id": user_data.user_id, "insight": insight}
                )
                self.logger.debug(
                    "Successfully analyzed user %s", user_data.user_id
                )

            except Exception as e:
                self.logger.error(
                    "Failed to analyze user %s: %s", user_data.user_id, e
                )

        self.logger.info("Analysis completed: %d users analyzed", len(results))
        return results

    async def _analyze_user_data(
        self, user_data: UserWeeklyData, context: AnalysisContext
    ) -> WeeklyUserTrendInsight:
        """특정 사용자 데이터 분석 - WeeklyUserTrendInsight 스키마 완전 적용"""

        # 모든 사용자에 대해 주간 전체 통계는 이미 계산됨
        user_weekly_stats = user_data.weekly_total_stats

        if user_data.weekly_new_posts:
            # 주간 새글이 있는 경우 - LLM 분석 실행
            (
                trending_items,
                trend_analysis,
            ) = await self._analyze_user_posts_with_llm(
                user_data.weekly_new_posts, user_data.username
            )
            user_weekly_reminder = None

        else:
            # 주간 새글이 없는 경우 - 리마인더 생성
            trending_items = []
            trend_analysis = None
            user_weekly_reminder = await self._create_user_reminder(
                user_data.user_id, context
            )

        # WeeklyUserTrendInsight 객체 생성
        return WeeklyUserTrendInsight(
            trending_summary=trending_items,  # WeeklyTrendInsight에서 상속
            trend_analysis=trend_analysis,  # WeeklyTrendInsight에서 상속
            user_weekly_stats=user_weekly_stats,  # WeeklyUserTrendInsight 고유 (항상 존재)
            user_weekly_reminder=user_weekly_reminder,  # WeeklyUserTrendInsight 고유
        )

    async def _save_results(
        self, results: list[dict], context: AnalysisContext
    ) -> None:
        """결과를 데이터베이스에 저장"""

        for result in results:
            try:
                user_id = result["user_id"]
                insight = result["insight"]

                # WeeklyUserTrendInsight 객체를 딕셔너리로 변환
                insight_data = insight.to_dict()

                await sync_to_async(UserWeeklyTrend.objects.create)(
                    user_id=user_id,
                    week_start_date=context.week_start.date(),
                    week_end_date=context.week_end.date(),
                    insight=insight_data,
                    is_processed=False,
                    processed_at=context.week_start,
                )

            except Exception as e:
                self.logger.error(
                    "Failed to save UserWeeklyTrend for user %s: %s",
                    user_id,
                    e,
                )

        self.logger.info(
            "Batch completed: %d records saved, %d users expired",
            len(results),
            len(self.expired_token_users),
        )

    async def run(self):
        """배치 실행"""
        result = await super().run()

        if result.metadata is None:
            result.metadata = {}

        result.metadata.update(
            {
                "expired_token_users": len(self.expired_token_users),
                "successful_users": len(self.successful_users),
                "expired_user_ids": list(self.expired_token_users),
            }
        )

        return result


async def main():
    """메인 실행 함수"""
    analyzer = UserWeeklyAnalyzer()
    result = await analyzer.run()

    if result.success:
        metadata = result.metadata or {}
        successful = metadata.get("successful_users", 0)
        expired = metadata.get("expired_token_users", 0)

        print("✅ 사용자 주간 분석 완료")
        print(f"   - 성공: {successful}명")
        print(f"   - 토큰 만료: {expired}명")

        if expired > 0:
            print(
                f"   ⚠️  토큰 만료 사용자: {metadata.get('expired_user_ids', [])}"
            )
    else:
        print(f"❌ 사용자 주간 분석 실패: {result.error}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
