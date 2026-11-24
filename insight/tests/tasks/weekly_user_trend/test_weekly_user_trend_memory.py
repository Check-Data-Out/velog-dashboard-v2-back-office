import logging
import tracemalloc
import uuid
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from scraping.velog.schemas import Post as VelogPost

MODULE = "insight.tasks.weekly_user_trend_analysis"
# 글 한 편의 본문 크기 (약 100KB)
BODY_SIZE = 100_000
TODAY = datetime(2026, 11, 23, tzinfo=ZoneInfo("Asia/Seoul"))


class FakeQuerySet:
    """호출을 기록하지 않는 가짜 ORM 체인.

    MagicMock 은 호출마다 인자를 쌓아 두어서 사용자 수만큼 메모리가 늘고,
    그 증가분이 측정에 섞인다. filter·exclude 같은 체인은 자신을 돌려주고
    끝에서 rows 를 내준다.
    """

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def __getattr__(self, name):
        return lambda *args, **kwargs: self

    def values(self, *fields):
        return [{field: row[field] for field in fields} for row in self.rows]

    def values_list(self, field, flat=True):
        return [row[field] for row in self.rows]

    def count(self):
        return len(self.rows)

    def create(self, **kwargs):
        return None


class FakeWeeklyTrend:
    week_start_date = date(2026, 11, 16)
    week_end_date = date(2026, 11, 22)

    def mark_batch(self, key: str) -> None:
        pass


class FakeVelogClient:
    async def get_post(self, post_uuid: str) -> VelogPost:
        return VelogPost(
            id=post_uuid,
            title="새 글",
            short_description="",
            # 부를 때마다 새 문자열을 만든다 (공유되는 상수가 아니다)
            body="x" * BODY_SIZE,
        )


def fake_analyze_user_posts(posts: list, api_key: str) -> dict:
    return {
        "trending_summary": [
            {"title": "새 글", "summary": "요약", "key_points": []}
        ],
        "trend_analysis": {},
    }


async def run_and_get_peak(module, user_count: int) -> int:
    """사용자 user_count 명(각자 이번 주 새 글 1편)을 분석하는 동안의 최대 메모리"""
    analyzer = module.UserWeeklyAnalyzer(FakeWeeklyTrend())
    # pytest 가 로그 레코드를 테스트 끝까지 모아 두므로 측정에서 뺀다
    analyzer.logger = logging.Logger("memory-test")
    analyzer.logger.addHandler(logging.NullHandler())

    users = [{"id": n, "username": f"user{n}"} for n in range(user_count)]
    posts = [{"id": 1, "post_uuid": uuid.uuid4()}]
    stats = [
        {
            "post_id": 1,
            "date": TODAY,
            "daily_view_count": 10,
            "daily_like_count": 1,
        }
    ]

    with (
        patch(f"{MODULE}.User.objects", FakeQuerySet(users)),
        patch(f"{MODULE}.Post.objects", FakeQuerySet(posts)),
        patch(f"{MODULE}.PostDailyStatistics.objects", FakeQuerySet(stats)),
        patch(f"{MODULE}.UserWeeklyTrend.objects", FakeQuerySet([])),
        patch(f"{MODULE}.analyze_user_posts", fake_analyze_user_posts),
        patch("insight.tasks.base_analysis.VelogClient") as client_cls,
    ):
        client_cls.get_client.return_value = FakeVelogClient()

        tracemalloc.start()
        try:
            result = await analyzer.run()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

    assert result.metadata["processed_count"] == user_count
    return peak


@pytest.mark.asyncio
class TestWeeklyUserTrendMemory:
    async def test_peak_memory_does_not_grow_with_user_count(
        self, user_trend_module
    ):
        """사용자가 20명에서 200명으로 늘어도 최대 메모리는 본문 2편 크기만큼도 늘지 않는다"""
        # 첫 실행에만 생기는 할당(스레드 풀·캐시)을 측정 전에 치른다
        await run_and_get_peak(user_trend_module, 1)

        peak_20 = await run_and_get_peak(user_trend_module, 20)
        peak_200 = await run_and_get_peak(user_trend_module, 200)

        assert peak_200 - peak_20 < 2 * BODY_SIZE
