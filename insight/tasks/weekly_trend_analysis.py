"""
[25.07.01] 주간 트렌드 분석 배치 (작성자: 이지현)
- 실행은 아래와 같은 커멘드 활용
- poetry run python ./insight/tasks/weekly_trend_analysis.py

[25.07.12] 주간 트렌드 분석 배치 (작성자: 정현우)
- class based 와 전체적인 구조 리펙토링
"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings

from insight.filtering.pipeline import classify_post
from insight.filtering.schemas import VERDICT_BORDERLINE, VERDICT_DROP
from insight.models import (
    REVIEW_NEEDS,
    REVIEW_READY,
    TrendAnalysis,
    TrendingItem,
    WeeklyTrend,
    WeeklyTrendInsight,
)
from insight.tasks.base_analysis import AnalysisContext, BaseBatchAnalyzer
from insight.tasks.weekly_llm_analyzer import analyze_trending_posts
from scraping.velog.schemas import Post


@dataclass
class TrendingPostData:
    """트렌딩 게시글 데이터"""

    post: Post
    body: str
    tags: list[str] = field(default_factory=list)

    def to_llm_format(self) -> dict[str, Any]:
        """LLM 분석용 포맷으로 변환"""
        return {
            "제목": self.post.title,
            "내용": self.body,
            # "조회수": self.post.views, # 실제 데이터 없음 (모두 0으로 들어감, 추후 추가 여부 논의)
            "좋아요 수": self.post.likes,
        }

    def to_meta_format(self) -> dict[str, str]:
        """메타데이터 포맷으로 변환"""
        return {
            "title": self.post.title,
            "username": self.post.user.username if self.post.user else "",
            "thumbnail": self.post.thumbnail or "",
            "slug": self.post.url_slug or "",
        }


class WeeklyTrendAnalyzer(BaseBatchAnalyzer[WeeklyTrendInsight]):
    """주간 트렌드 분석기"""

    def __init__(self, trending_limit: int = 10):
        super().__init__()
        self.trending_limit = trending_limit
        # borderline 글 존재 시 발송 전 사람 검수가 필요함을 표시
        self.needs_review = False

    async def _fetch_data(
        self, context: AnalysisContext
    ) -> list[TrendingPostData]:
        """트렌딩 게시글 데이터 수집"""
        try:
            # 트렌딩 게시글 목록 조회
            trending_posts = await context.velog_client.get_trending_posts(
                limit=self.trending_limit
            )

            if not trending_posts:
                return []

            # 각 게시글의 본문 조회
            post_data_list = []
            for post in trending_posts:
                try:
                    detail = await context.velog_client.get_post(post.id)
                    body = detail.body if detail and detail.body else ""
                    tags = list(detail.tags) if detail and detail.tags else []

                    if not body:
                        self.logger.warning("Post %s has empty body", post.id)

                    post_data_list.append(
                        TrendingPostData(post=post, body=body, tags=tags)
                    )

                except Exception as e:
                    self.logger.warning(
                        "Failed to fetch post detail (id=%s): %s", post.id, e
                    )
                    # 본문 없이도 데이터 추가
                    post_data_list.append(
                        TrendingPostData(post=post, body="", tags=[])
                    )

            self.logger.info("Fetched %d trending posts", len(post_data_list))
            return post_data_list

        except Exception as e:
            self.logger.error("Failed to fetch trending posts: %s", e)
            raise

    def _filter_ad_posts(
        self, raw_data: list[TrendingPostData]
    ) -> list[TrendingPostData]:
        """광고/스팸(개발 무관 오프토픽)으로 판정된 글을 요약 전에 제거한다.

        휴리스틱 단독 경로(무클라이언트). drop 만 제외하고 borderline 은 보존한다.
        """
        survivors = []
        for post_data in raw_data:
            verdict = classify_post(
                body=post_data.body,
                title=post_data.post.title,
                tags=post_data.tags,
            )
            if verdict.verdict == VERDICT_DROP:
                self.logger.info(
                    "Filtered ad/spam post '%s' (%s)",
                    post_data.post.title,
                    verdict.triggered_signals,
                )
                continue
            if verdict.verdict == VERDICT_BORDERLINE:
                self.needs_review = True
                self.logger.info(
                    "Borderline post needs review: '%s' (%s)",
                    post_data.post.title,
                    verdict.triggered_signals,
                )
            survivors.append(post_data)
        return survivors

    async def _analyze_data(
        self, raw_data: list[TrendingPostData], context: AnalysisContext
    ) -> list[WeeklyTrendInsight]:
        """LLM을 사용한 트렌드 분석"""
        try:
            # 광고/스팸 글 제거 (drop 글은 물리적으로 빼서 인덱스 매핑 정합 유지)
            raw_data = self._filter_ad_posts(raw_data)
            if not raw_data:
                self.logger.warning(
                    "All posts filtered as ad/spam, empty insight"
                )
                return [WeeklyTrendInsight()]

            # LLM 입력 데이터 준비
            llm_input = [post_data.to_llm_format() for post_data in raw_data]

            # LLM 분석 실행
            llm_result = analyze_trending_posts(
                llm_input, settings.OPENAI_API_KEY
            )

            # 결과 파싱
            trending_summary_raw = llm_result.get("trending_summary", [])
            trend_analysis_raw = llm_result.get("trend_analysis", {})

            # TrendingItem 객체 생성
            trending_items = []
            for i, post_data in enumerate(raw_data):
                meta = post_data.to_meta_format()
                summary_item = (
                    trending_summary_raw[i]
                    if i < len(trending_summary_raw)
                    else {}
                )

                trending_item = TrendingItem(
                    title=meta["title"],
                    summary=summary_item.get("summary", ""),
                    key_points=summary_item.get("key_points", []),
                    username=meta["username"],
                    thumbnail=meta["thumbnail"],
                    slug=meta["slug"],
                )
                trending_items.append(trending_item)

            # TrendAnalysis 객체 생성
            trend_analysis = TrendAnalysis(
                hot_keywords=trend_analysis_raw.get("hot_keywords", []),
                title_trends=trend_analysis_raw.get("title_trends", ""),
                content_trends=trend_analysis_raw.get("content_trends", ""),
                insights=trend_analysis_raw.get("insights", ""),
            )

            result = WeeklyTrendInsight(
                trending_summary=trending_items, trend_analysis=trend_analysis
            )

            self.logger.info(
                "Trend analysis completed: %s items", len(trending_items)
            )
            return [result]  # 주간 트렌드는 하나의 결과만 생성

        except Exception as e:
            self.logger.error("LLM analysis failed: %s", e)
            raise

    async def _save_results(
        self, results: list[WeeklyTrendInsight], context: AnalysisContext
    ) -> None:
        """결과를 데이터베이스에 저장"""
        if not results:
            return

        result = results[0]  # 주간 트렌드는 하나의 결과만 있음

        try:
            # WeeklyTrendInsight 형태로 변환
            insight_data = {
                "trending_summary": [
                    item.to_dict() for item in result.trending_summary
                ],
                "trend_analysis": (
                    result.trend_analysis.to_dict()
                    if result.trend_analysis
                    else {}
                ),
            }

            await sync_to_async(WeeklyTrend.objects.create)(
                week_start_date=context.week_start.date(),
                week_end_date=(context.week_end - timedelta(days=1)).date(),
                insight=insight_data,
                is_processed=False,
                processed_at=context.week_end,
                review_status=(
                    REVIEW_NEEDS if self.needs_review else REVIEW_READY
                ),
            )

            self.logger.info("WeeklyTrend saved successfully")

        except Exception as e:
            self.logger.error("Failed to save WeeklyTrend: %s", e)
            raise


async def main():
    """메인 실행 함수"""
    analyzer = WeeklyTrendAnalyzer(trending_limit=10)
    result = await analyzer.run()

    if result.success:
        try:
            with open("weekly_analysis_result.txt", "w") as f:
                f.write(f"✅ 주간 트렌드 분석 완료: {result.metadata}\\n")
        except Exception as e:
            print(f"결과 파일 저장 실패: {e}")
    else:
        try:
            with open("weekly_analysis_result.txt", "w") as f:
                f.write(f"❌ 주간 트렌드 분석 실패: {result.error}\\n")
        except Exception as e:
            print(f"결과 파일 저장 실패: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
