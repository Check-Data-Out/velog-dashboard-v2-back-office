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
from typing import Any

import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Q

from insight.models import TrendingItem, UserWeeklyTrend
from insight.tasks.base_analysis import AnalysisContext, BaseBatchAnalyzer
from insight.tasks.weekly_llm_analyzer import analyze_user_posts
from posts.models import Post, PostDailyStatistics
from scraping.velog.schemas import Post as VelogPost
from users.models import User


class TokenExpiredError(Exception):
    """토큰 만료 예외"""

    def __init__(
        self,
        user_id: int,
        message: str = "Token expired or data inconsistency detected",
    ):
        self.user_id = user_id
        self.message = message
        super().__init__(message)


@dataclass
class UserPostData:
    """사용자 게시글 데이터"""

    user_id: int
    username: str
    post: VelogPost
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

    def __init__(self):
        super().__init__()
        self.expired_token_users = set()  # 토큰 만료된 사용자 추적
        self.successful_users = set()  # 성공한 사용자 추적

    async def _fetch_data(
        self, context: AnalysisContext
    ) -> list[UserPostData]:
        """사용자별 게시글 데이터 수집 - 토큰 만료 사용자 제외"""
        try:
            # 활성 사용자 목록 조회
            users = await sync_to_async(list)(
                User.objects.filter(
                    email__isnull=False,
                    is_active=True,
                    id__in=[
                        244,
                        167,
                        77,
                        8,
                        1,
                    ],
                )
                .exclude(email="")
                .values("id", "username")
            )

            active_user_posts = []
            total_users = len(users)

            self.logger.info("Starting analysis for %d users", total_users)

            for user in users:
                user_id = user["id"]
                try:
                    user_posts = await self._fetch_user_posts(user_id, context)
                    if user_posts:  # 게시글이 있는 사용자만 추가
                        active_user_posts.extend(user_posts)
                        self.successful_users.add(user_id)
                        self.logger.debug(
                            "Successfully fetched %d posts for user %s",
                            len(user_posts),
                            user_id,
                        )

                except TokenExpiredError:
                    # 토큰 만료된 사용자는 expired_token_users에 추가
                    self.expired_token_users.add(user_id)
                    self.logger.warning(
                        "Token expired for user %s, excluding from analysis",
                        user_id,
                    )
                    continue

                except Exception as e:
                    self.logger.warning(
                        "Failed to fetch posts for user %s: %s", user_id, e
                    )
                    continue

            # 최종 통계 로깅
            successful_count = len(self.successful_users)
            expired_count = len(self.expired_token_users)
            failed_count = total_users - successful_count - expired_count

            self.logger.info(
                "Data collection completed: %d total users, %d successful (%.1f%%), "
                "%d token expired (%.1f%%), %d other failures (%.1f%%)",
                total_users,
                successful_count,
                successful_count / total_users * 100,
                expired_count,
                expired_count / total_users * 100,
                failed_count,
                failed_count / total_users * 100,
            )

            return active_user_posts

        except Exception as e:
            self.logger.error("Failed to fetch user data: %s", e)
            raise

    async def _fetch_user_posts(
        self, user_id: int, context: AnalysisContext
    ) -> list[UserPostData]:
        """특정 사용자의 게시글 데이터 수집 - 토큰 만료 시 예외 발생"""

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
            # 게시글이 없는 것은 정상 상황 (빈 리스트 반환)
            return []

        # 통계 데이터 조회, where 절 순서 명확성을 위해 Q 객체 사용
        post_ids = [p["id"] for p in posts]
        stats_qs = await sync_to_async(list)(
            PostDailyStatistics.objects.filter(
                Q(post_id__in=post_ids)
                & Q(date__in=[context.week_start, context.week_end])
            )
            .values("post_id", "date", "daily_view_count", "daily_like_count")
            .order_by("id")
        )
        # 절대 명심, stats_qs 는 무조건 2개거나 1개임!!!

        # 통계 데이터 매핑
        stats_by_post = defaultdict(dict)
        for stat in stats_qs:
            stats_by_post[stat["post_id"]][stat["date"]] = {
                "view": stat["daily_view_count"],
                "like": stat["daily_like_count"],
            }

        user_posts = []
        for post_data in posts:
            post_id = post_data["id"]
            post_uuid = post_data["post_uuid"]
            username = post_data["user__username"]

            # 이미 검사된 통계 데이터 재사용
            stat_map = stats_by_post.get(post_id, {})
            today_stats = stat_map.get(context.week_end, {})
            prev_stats = stat_map.get(context.week_start, {})

            if not prev_stats:
                view_diff = today_stats.get("view", 0)
                like_diff = today_stats.get("like", 0)
            else:
                view_diff = (today_stats.get("view", 0)) - (
                    prev_stats.get("view", 0)
                )
                like_diff = (today_stats.get("like", 0)) - (
                    prev_stats.get("like", 0)
                )

            # 토큰 만료 감지 시 즉시 예외 발생 (해당 사용자 분석 제외)
            if view_diff < 0 or like_diff < 0:
                raise TokenExpiredError(user_id=user_id)

            try:
                # Velog에서 게시글 본문 조회
                velog_post = await context.velog_client.get_post(
                    str(post_uuid)
                )
                body = (
                    velog_post.body if velog_post and velog_post.body else ""
                )

                user_post = UserPostData(
                    user_id=user_id,
                    username=username,
                    post=velog_post,
                    body=body,
                    view_diff=view_diff,
                    like_diff=like_diff,
                )
                user_posts.append(user_post)

            except Exception as e:
                # Velog API 호출 실패는 해당 게시글만 제외 (사용자 전체는 유지)
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
        """사용자별 데이터 분석 - 토큰 만료 사용자는 이미 제외됨"""

        # 사용자별로 데이터 그룹핑
        user_posts_map = defaultdict(list)
        for user_post in raw_data:
            user_posts_map[user_post.user_id].append(user_post)

        results = []
        analyzed_users = len(user_posts_map)

        self.logger.info(
            "Starting analysis for %d users with valid data", analyzed_users
        )

        for user_id, user_posts in user_posts_map.items():
            try:
                result = await self._analyze_user_posts(user_id, user_posts)
                if result:
                    results.append(result)
                    self.logger.debug("Successfully analyzed user %s", user_id)

            except Exception as e:
                self.logger.error(
                    "Failed to analyze posts for user %s: %s", user_id, e
                )
                continue

        self.logger.info(
            "Analysis completed: %d/%d users successfully analyzed",
            len(results),
            analyzed_users,
        )
        return results

    async def _analyze_user_posts(
        self, user_id: int, user_posts: list[UserPostData]
    ) -> UserWeeklyResult:
        """특정 사용자의 게시글 분석"""
        if not user_posts:
            return None

        # 통계 요약
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
                        thumbnail=user_post.post.thumbnail,
                        slug=user_post.post.url_slug,
                    )
                    trending_items.append(trending_item)

            except Exception as e:
                self.logger.warning(
                    "LLM analysis failed for user %s post %s: %s",
                    user_id,
                    user_post.post.id,
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
        """결과를 데이터베이스에 저장 - 토큰 만료 사용자는 저장하지 않음"""

        for result in results:
            try:
                insight_data = {
                    "trending_summary": [
                        item.to_dict() for item in result.trending_items
                    ],
                    "trend_analysis": {"summary": result.simple_summary},
                }

                await sync_to_async(UserWeeklyTrend.objects.create)(
                    user_id=result.user_id,
                    week_start_date=context.week_start.date(),
                    week_end_date=context.week_end.date(),
                    insight=insight_data,
                    is_processed=False,
                    processed_at=context.week_start,
                )

            except Exception as e:
                self.logger.error(
                    "Failed to save UserWeeklyTrend for user %s: %s",
                    result.user_id,
                    e,
                )
                continue

        # 최종 결과 로깅
        saved_count = len(results)
        expired_count = len(self.expired_token_users)

        self.logger.info(
            "Batch completed: %d UserWeeklyTrend records saved, %d users skipped due to token expiry",
            saved_count,
            expired_count,
        )

        # 토큰 만료 사용자 목록 로깅 (디버깅용)
        if self.expired_token_users:
            self.logger.debug(
                "Expired token users: %s", list(self.expired_token_users)
            )

    async def run(self):
        """배치 실행 - 토큰 만료 통계 포함"""
        result = await super().run()

        # 메타데이터에 토큰 만료 정보 추가
        if result.metadata is None:
            result.metadata = {}

        result.metadata.update(
            {
                "expired_token_users": len(self.expired_token_users),
                "successful_users": len(self.successful_users),
                "expired_user_ids": (
                    list(self.expired_token_users)
                    if self.expired_token_users
                    else []
                ),
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
