import pytest

from insight.admin import JsonPreviewMixin
from insight.models import UserWeeklyTrend, WeeklyTrend


@pytest.mark.django_db
class TestJsonPreviewMixin:
    """JsonPreviewMixin 테스트"""

    def test_get_json_preview(self, weekly_trend: WeeklyTrend):
        """get_json_preview 메소드 테스트"""
        mixin = JsonPreviewMixin()
        preview = mixin.get_json_preview(weekly_trend, "insight", 50)

        assert isinstance(preview, str)
        assert len(preview) <= 50
        # 길이 제한으로 인해 원본보다 짧은지 확인
        assert len(preview) < len(str(weekly_trend.insight))

    def test_get_json_preview_empty(self, empty_insight_weekly_trend):
        """빈 JSON 데이터에 대한 get_json_preview 테스트"""
        mixin = JsonPreviewMixin()
        preview = mixin.get_json_preview(empty_insight_weekly_trend, "insight")
        assert preview == "-"

    def test_formatted_insight_weekly_trend(
        self, weekly_trend: WeeklyTrend, sample_trend_analysis
    ):
        """WeeklyTrend의 formatted_insight 테스트"""
        mixin = JsonPreviewMixin()
        result = mixin.formatted_insight(weekly_trend)

        assert "트렌드 분석" in result
        assert "핵심 키워드" in result
        for keyword in sample_trend_analysis.hot_keywords:
            assert keyword in result
        assert "트렌딩 요약" in result

    def test_formatted_insight_user_weekly_trend(
        self, user_weekly_trend: UserWeeklyTrend, sample_trend_analysis
    ):
        """UserWeeklyTrend의 formatted_insight 테스트"""
        mixin = JsonPreviewMixin()
        result = mixin.formatted_insight(user_weekly_trend)

        assert "사용자 주간 통계" in result
        assert "트렌드 분석" in result
        assert "핵심 키워드" in result
        for keyword in sample_trend_analysis.hot_keywords:
            assert keyword in result
        assert "작성 게시글 요약" in result
        assert "Django 모델 최적화하기" in result

    def test_formatted_insight_user_weekly_trend_with_reminder(
        self, inactive_user_weekly_trend: UserWeeklyTrend
    ):
        """주간 글 미작성 UserWeeklyTrend의 formatted_insight 테스트"""
        mixin = JsonPreviewMixin()
        result = mixin.formatted_insight(inactive_user_weekly_trend)

        assert "리마인더" in result
        assert "사용자 주간 통계" in result
        assert "트렌드 분석" not in result
        assert "핵심 키워드" not in result
        assert "작성 게시글 요약" not in result

    def test_formatted_insight_empty(self, empty_insight_weekly_trend):
        """빈 인사이트 데이터에 대한 formatted_insight 테스트"""
        mixin = JsonPreviewMixin()
        result = mixin.formatted_insight(empty_insight_weekly_trend)
        assert result == "-"
