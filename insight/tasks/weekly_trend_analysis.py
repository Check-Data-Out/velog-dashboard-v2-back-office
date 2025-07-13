"""
[25.07.01] 주간 트렌드 분석 배치 (작성자: 이지현)
- 실행은 아래와 같은 커멘드 활용
- poetry run python ./insight/tasks/weekly_trend_analysis.py

[25.07.12] 주간 트렌드 분석 배치 (작성자: 정현우)
- class based 와 전체적인 구조 리펙토링
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import setup_django  # noqa
from asgiref.sync import sync_to_async
from django.conf import settings

from insight.models import (
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

    def to_llm_format(self) -> dict[str, Any]:
        """LLM 분석용 포맷으로 변환"""
        return {
            "제목": self.post.title,
            "내용": self.body,
            "조회수": self.post.views,
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

                    if not body:
                        self.logger.warning("Post %s has empty body", post.id)

                    post_data_list.append(
                        TrendingPostData(post=post, body=body)
                    )

                except Exception as e:
                    self.logger.warning(
                        "Failed to fetch post detail (id=%s): %s", post.id, e
                    )
                    # 본문 없이도 데이터 추가
                    post_data_list.append(TrendingPostData(post=post, body=""))

            self.logger.info("Fetched %d trending posts", len(post_data_list))
            return post_data_list

        except Exception as e:
            self.logger.error("Failed to fetch trending posts: %s", e)
            raise

    async def _analyze_data(
        self, raw_data: list[TrendingPostData], context: AnalysisContext
    ) -> list[WeeklyTrendInsight]:
        """LLM을 사용한 트렌드 분석"""
        try:
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
                "trend_analysis": result.trend_analysis.to_dict(),
            }

            await sync_to_async(WeeklyTrend.objects.create)(
                week_start_date=context.week_start.date(),
                week_end_date=context.week_end.date(),
                insight=insight_data,
                is_processed=False,
                processed_at=context.week_start,
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
        print(f"✅ 주간 트렌드 분석 완료: {result.metadata}")
    else:
        print(f"❌ 주간 트렌드 분석 실패: {result.error}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
