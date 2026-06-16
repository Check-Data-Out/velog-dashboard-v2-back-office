from unittest.mock import MagicMock

import pytest


def _post(body, title, tags=None):
    """TrendingPostData 형태를 흉내내는 mock (top-level import 회피)."""
    item = MagicMock(body=body, tags=tags or [])
    item.post.title = title
    return item


@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyTrendFilter:
    def test_filter_ad_posts_removes_drop_keeps_dev(self, analyzer):
        """오프토픽 광고는 제거하고 개발 글은 보존한다(요약 전 물리 제거)."""
        spam = _post("노래방 도우미 급구 010-1234-5678", "광고")
        dev = _post(
            "리액트 서버 배포 api 도커로 구현 테스트", "개발글", ["react"]
        )

        survivors = analyzer._filter_ad_posts([spam, dev])

        assert survivors == [dev]

    @pytest.mark.asyncio
    async def test_all_dropped_yields_empty_insight(self, analyzer):
        """전량 광고로 판정되면 크래시 없이 빈 인사이트를 반환한다."""
        spam = _post("온라인카지노 사설토토 꽁머니 지급", "도박광고")

        result = await analyzer._analyze_data([spam], MagicMock())

        assert result[0].trending_summary == []
