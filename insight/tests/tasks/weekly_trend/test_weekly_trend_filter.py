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

    def test_borderline_post_flagged_but_not_dropped(self, analyzer):
        """borderline 글은 발송에서 빠지지 않고(survivor 유지) 프리뷰 플래그만 선다."""
        borderline = _post("오늘 날씨가 좋아서 산책을 다녀왔습니다", "일상")

        survivors = analyzer._filter_ad_posts([borderline])

        assert survivors == [borderline]  # 기본 흐름대로 발송 대상에 남는다
        assert (
            analyzer.has_borderline is True
        )  # 검수 권장 표시(발송은 막지 않음)

    def test_filter_preview_records_all_verdicts(self, analyzer):
        """프리뷰에 drop/pass 후보가 판정과 함께 누적된다(Slack 검수용)."""
        spam = _post("노래방 도우미 급구 010-1234-5678", "광고")
        dev = _post("리액트 서버 배포 api 도커 구현 테스트", "개발", ["react"])

        analyzer._filter_ad_posts([spam, dev])

        assert len(analyzer.filter_preview) == 2
        verdicts = {row["verdict"].verdict for row in analyzer.filter_preview}
        assert "drop" in verdicts

    def test_clean_dev_post_no_borderline_flag(self, analyzer):
        """명확한 개발 글만 있으면 검수 권장 플래그가 서지 않는다."""
        dev = _post(
            "리액트 서버 배포 api 도커 구현 테스트 자동화", "개발", ["react"]
        )

        analyzer._filter_ad_posts([dev])

        assert analyzer.has_borderline is False

    @pytest.mark.asyncio
    async def test_all_dropped_yields_empty_insight(self, analyzer):
        """전량 광고로 판정되면 크래시 없이 빈 인사이트를 반환한다."""
        spam = _post("온라인카지노 사설토토 꽁머니 지급", "도박광고")

        result = await analyzer._analyze_data([spam], MagicMock())

        assert result[0].trending_summary == []
