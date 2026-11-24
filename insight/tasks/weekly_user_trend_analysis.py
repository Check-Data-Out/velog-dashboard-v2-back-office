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
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.db.models import Q
from django.utils import timezone

from insight.models import (
    BATCH_USER_ANALYSIS_COMPLETED,
    BATCH_USER_ANALYSIS_STARTED,
    TrendAnalysis,
    TrendingItem,
    UserWeeklyTrend,
    WeeklyTrend,
    WeeklyUserReminder,
    WeeklyUserStats,
    WeeklyUserTrendInsight,
)
from insight.tasks.base_analysis import (
    AnalysisContext,
    AnalysisResult,
    BaseBatchAnalyzer,
)
from insight.tasks.wait_daily_stats import (
    fetch_today_success_runs,
    wait_for_daily_stats,
)
from insight.tasks.weekly_llm_analyzer import analyze_user_posts
from posts.models import Post, PostDailyStatistics
from scraping.velog.schemas import Post as VelogPost
from users.models import User
from utils.utils import record_peak_memory, to_local_date

logger = logging.getLogger("newsletter")

# 할 일 없이 끝났음을 실행 스크립트에 알리는 표시 파일 (현재 폴더)
SKIP_MARKER = "weekly_user_trend_analysis.skipped"


def _to_local_midnight(day: date) -> datetime:
    """day 의 00:00 (Django 현재 시간대, KST)"""
    return timezone.make_aware(datetime.combine(day, datetime.min.time()))


def _skip_when_completed(weekly_trend: WeeklyTrend) -> bool:
    """이번 주 사용자 분석이 이미 끝났으면 건너뜀 줄과 표시 파일을 남기고 True"""
    if not weekly_trend.batch_value(BATCH_USER_ANALYSIS_COMPLETED):
        return False
    with open("weekly_analysis_result.txt", "a") as f:
        f.write("⏭ 사용자 주간 분석 건너뜀: 이번 주 분석이 이미 끝남\n")
    Path(SKIP_MARKER).touch()
    return True


@dataclass
class UserWeeklyData:
    """사용자 주간 데이터"""

    user_id: int
    username: str
    weekly_new_posts: list[VelogPost]  # 주간 새글 (LLM 분석용)
    weekly_total_stats: WeeklyUserStats  # 주간 전체 통계


class UserWeeklyAnalyzer(BaseBatchAnalyzer[dict]):
    """사용자별 주간 분석기"""

    def __init__(self, weekly_trend: WeeklyTrend):
        """
        Args:
            weekly_trend: 이번 주 공통 분석 행. 분석 주차와 시작·완료 표시의 기준이다.
        """
        super().__init__()
        self.weekly_trend = weekly_trend
        self.expired_token_users = set()
        self.successful_users = set()
        self.failed_users = set()
        self.all_target_users = set()

    async def _initialize_context(self) -> AnalysisContext:
        """분석 컨텍스트 초기화.

        주차를 오늘이 아니라 이번 주 공통 분석 행에서 가져온다. 그래서 다른
        요일에 다시 돌려도 같은 주차로 계산하고 저장한다.
        """
        context = await super()._initialize_context()
        context.week_start = _to_local_midnight(
            self.weekly_trend.week_start_date
        )
        context.week_end = _to_local_midnight(
            self.weekly_trend.week_end_date + timedelta(days=1)
        )
        return context

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
            context.week_end.date()
            - to_local_date(last_post.released_at).date()
        ).days
        if days_ago == 0:
            return None  # 배치 당일 발행 글은 다음 뉴스레터에 포함됨, 리마인더 미표시
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

    async def _fetch_data(self, context: AnalysisContext) -> list[dict]:
        """분석 대상 사용자 목록(id, username) 조회.

        분석 주차의 결과가 이미 저장된 사용자는 뺀다. 그래서 중간에 끊긴
        실행을 다시 돌리면 남은 사용자만 처리한다.
        """
        users = await sync_to_async(list)(
            User.objects.filter(
                email__isnull=False,
                is_active=True,
                newsletter_subscribed=True,
            )
            .exclude(email="")
            .exclude(
                id__in=UserWeeklyTrend.objects.filter(
                    week_end_date=self.weekly_trend.week_end_date
                ).values("user_id")
            )
            .values("id", "username")
        )

        self.all_target_users = {user["id"] for user in users}
        return users

    async def _process_user(
        self, user_id: int, username: str, context: AnalysisContext
    ) -> bool:
        """사용자 한 명을 수집 → 분석 → 저장한다.

        본문 참조가 이 함수 안에서 끝나므로, 동시에 메모리에 있는 본문은
        한 명분이다.

        Returns:
            분석했으면 True. 토큰이 만료됐거나 실패하면 False.
            예외로 실패한 사용자는 failed_users 에 남긴다.
        """
        try:
            user_data = await self._collect_user_data(
                user_id, username, context
            )
            if user_data is None:
                return False

            results = await self._analyze_data([user_data], context)
            await self._save_results(results, context)
            return bool(results)

        except Exception as e:
            self.logger.warning("Failed to process user %s: %s", user_id, e)
            self.successful_users.discard(user_id)
            self.failed_users.add(user_id)
            return False

    async def _collect_user_data(
        self, user_id: int, username: str, context: AnalysisContext
    ) -> UserWeeklyData | None:
        """사용자 한 명의 주간 데이터 수집. 토큰이 만료됐으면 None"""
        # 토큰 유효성 확인
        if not await self._check_user_token_validity(user_id, context):
            self.expired_token_users.add(user_id)
            return None

        # 토큰이 유효하면 successful_users에 추가
        self.successful_users.add(user_id)

        # 1. 주간 새글 수집 (LLM 분석용)
        weekly_new_posts = await self._fetch_user_weekly_new_posts(
            user_id, context
        )

        # 2. 주간 전체 통계 계산
        weekly_total_stats = await self._calculate_user_weekly_total_stats(
            user_id, context
        )

        self.logger.debug(
            "Collected data for user %s: %d new posts, stats(posts=%d, new_posts=%d, views=%d, likes=%d)",
            user_id,
            len(weekly_new_posts),
            weekly_total_stats.posts,
            weekly_total_stats.new_posts,
            weekly_total_stats.views,
            weekly_total_stats.likes,
        )

        return UserWeeklyData(
            user_id=user_id,
            username=username,
            weekly_new_posts=weekly_new_posts,
            weekly_total_stats=weekly_total_stats,
        )

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
                    week_end_date=(
                        context.week_end - timedelta(days=1)
                    ).date(),
                    insight=insight_data,
                    is_processed=False,
                    processed_at=context.week_end,
                )

            except Exception as e:
                self.logger.error(
                    "Failed to save UserWeeklyTrend for user %s: %s",
                    user_id,
                    e,
                )

    async def _process(
        self, context: AnalysisContext
    ) -> AnalysisResult[list[dict]]:
        """본처리.

        전원의 본문을 한꺼번에 쌓지 않도록 사용자 한 명씩 수집 → 분석 →
        저장한다. 그래서 결과(data)는 모아 두지 않는다.
        """
        await sync_to_async(self.weekly_trend.mark_batch)(
            BATCH_USER_ANALYSIS_STARTED
        )

        users = await self._fetch_data(context)
        self.logger.info("Starting analysis for %d users", len(users))

        processed_count = 0
        for user in users:
            if await self._process_user(user["id"], user["username"], context):
                processed_count += 1

        # 사용자별 실패가 이번 실행 대상의 절반 이상이면(OpenAI·DB 장애 등)
        # 완료 표시 없이 실패로 끝낸다. 뉴스레터는 완료 표시가 있어야 보내므로
        # 개인 통계 없는 메일이 전원에게 나가지 않는다
        failed_count = len(self.failed_users)
        if users and failed_count * 2 >= len(users):
            raise Exception(
                f"사용자별 실패 {failed_count}명 / 이번 실행 대상 {len(users)}명 (절반 이상). "
                "완료 표시를 남기지 않음. 다시 돌리면 결과가 없는 사용자만 분석하며, "
                "그 사용자들이 계속 실패하면 완료되지 않음"
            )

        # 실패가 절반 미만이면 로그만 남기고, 대상 전원을 다 돌았으면 완료로 본다
        await sync_to_async(self.weekly_trend.mark_batch)(
            BATCH_USER_ANALYSIS_COMPLETED
        )

        self.logger.info(
            "Batch completed: %d users analyzed, %d users expired",
            processed_count,
            len(self.expired_token_users),
        )
        return AnalysisResult(
            success=True,
            data=[],
            metadata={"processed_count": processed_count},
        )

    async def run(self) -> AnalysisResult[list[dict]]:
        """배치 실행. 성공·실패 모두 사용자 집계를 metadata 에 붙인다"""
        result = await super().run()
        result.metadata = {
            **(result.metadata or {}),
            "expired_token_users": len(self.expired_token_users),
            "successful_users": len(self.successful_users),
            "failed_users": len(self.failed_users),
            "expired_user_ids": list(self.expired_token_users),
        }
        return result


async def main():
    """메인 실행 함수"""
    # 지난 실행이 남긴 건너뜀 표시를 지운다
    Path(SKIP_MARKER).unlink(missing_ok=True)

    # 공통 분석이 먼저다. 이번 주 행이 없으면 주차를 정할 수 없다
    weekly_trend = await sync_to_async(
        WeeklyTrend.objects.this_week().order_by("-week_end_date").first
    )()
    if weekly_trend is None:
        with open("weekly_analysis_result.txt", "a") as f:
            f.write(
                "❌ 사용자 주간 분석 실패: 이번 주 공통 분석 결과가 없음\n"
            )
        return 1

    # 이미 끝난 주는 세션·velog·LLM 을 건드리기 전에 끝낸다
    if _skip_when_completed(weekly_trend):
        return 0

    # 기다리는 동안(최대 90분) 쉬는 DB 연결은 서버가 끊을 수 있다.
    # 닫아 두면 분석이 새 연결을 연다. 연결은 스레드마다 따로라서
    # 쿼리를 돌린 스레드에서 닫는다
    await sync_to_async(connections.close_all)()

    # 개인 통계는 주차가 끝난 다음 날(월요일)의 일일 통계로 만든다.
    # 그날 세트가 다 모일 때까지 기다린다
    wait_for_daily_stats(
        _to_local_midnight(weekly_trend.week_end_date + timedelta(days=1)),
        fetch_today_success_runs,
        time.sleep,
        time.monotonic,
        logger,
    )

    analyzer = UserWeeklyAnalyzer(weekly_trend)
    result = await analyzer.run()

    if result.success:
        metadata = result.metadata or {}
        successful = metadata.get("successful_users", 0)
        expired = metadata.get("expired_token_users", 0)
        failed = metadata.get("failed_users", 0)

        # 결과 파일 저장 (for slack notification)
        try:
            with open("weekly_analysis_result.txt", "a") as f:
                f.write(
                    f"✅ 사용자 주간 분석 완료: 성공 {successful}명, 토큰 만료 {expired}명, 실패 {failed}명\\n"
                )
                f.write(
                    f"   - 토큰 만료 사용자: {metadata.get('expired_user_ids', [])}"
                )
        except Exception as e:
            print(f"결과 파일 저장 실패: {e}")
    else:
        try:
            with open("weekly_analysis_result.txt", "a") as f:
                f.write(f"❌ 사용자 주간 분석 실패: {result.error}")
        except Exception as e:
            print(f"결과 파일 저장 실패: {e}")

    record_peak_memory(logger, "weekly_analysis_result.txt")

    return 0 if result.success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
