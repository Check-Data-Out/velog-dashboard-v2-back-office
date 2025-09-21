# poetry run pytest insight/tests/test_weekly_trend_admin.py -v
from unittest.mock import patch

import pytest
from django.utils.safestring import SafeString

from insight.models import WeeklyTrend
from utils.utils import get_local_now


@pytest.mark.django_db
class TestWeeklyTrendAdmin:
    """WeeklyTrendAdmin 테스트"""

    def test_week_range(self, weekly_trend_admin, weekly_trend: WeeklyTrend):
        """week_range 메소드 테스트"""
        result = weekly_trend_admin.week_range(weekly_trend)
        expected_format = f"{weekly_trend.week_start_date.strftime('%Y-%m-%d')} ~ {weekly_trend.week_end_date.strftime('%Y-%m-%d')}"
        assert expected_format in result

    def test_is_processed_colored_true(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """is_processed_colored 메소드 테스트 (처리 완료)"""
        weekly_trend.is_processed = True
        weekly_trend.save()

        result = weekly_trend_admin.is_processed_colored(weekly_trend)
        assert "green" in result
        assert "✓" in result

    def test_is_processed_colored_false(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """is_processed_colored 메소드 테스트 (미처리)"""
        weekly_trend.is_processed = False
        weekly_trend.save()

        result = weekly_trend_admin.is_processed_colored(weekly_trend)
        assert "red" in result
        assert "✗" in result

    def test_processed_at_formatted_with_date(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 있음)"""
        now = get_local_now()
        weekly_trend.processed_at = now
        weekly_trend.save()

        result = weekly_trend_admin.processed_at_formatted(weekly_trend)
        assert now.strftime("%Y-%m-%d %H:%M") == result

    def test_processed_at_formatted_no_date(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 없음)"""
        weekly_trend.processed_at = None
        weekly_trend.save()

        result = weekly_trend_admin.processed_at_formatted(weekly_trend)
        assert result == "-"

    def test_summarize_insight_with_data(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """summarize_insight 메소드 테스트 (데이터 있음)"""
        result = weekly_trend_admin.summarize_insight(weekly_trend)

        # trending_summary 개수 확인
        summary_count = len(weekly_trend.insight.get("trending_summary", []))
        assert f"요약: {summary_count}개" in result

        # 키워드 확인
        keywords = weekly_trend.insight.get("trend_analysis", {}).get(
            "hot_keywords", []
        )
        if keywords:
            assert "키워드:" in result
            assert keywords[0] in result

    def test_summarize_insight_no_data(
        self, weekly_trend_admin, empty_insight_weekly_trend: WeeklyTrend
    ):
        """summarize_insight 메소드 테스트 (데이터 없음)"""
        result = weekly_trend_admin.summarize_insight(
            empty_insight_weekly_trend
        )
        assert "요약: 0개" in result

    def test_summarize_insight_non_dict(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """summarize_insight 메소드 테스트 (비딕셔너리 데이터)"""
        weekly_trend.insight = "invalid_data"
        weekly_trend.save()

        result = weekly_trend_admin.summarize_insight(weekly_trend)
        assert result == "데이터 없음"

    @patch("insight.admin.weekly_trend_admin.render_to_string")
    def test_render_full_preview_success(
        self,
        mock_render_to_string,
        weekly_trend_admin,
        weekly_trend: WeeklyTrend,
    ):
        """render_full_preview 메소드 테스트 (성공)"""
        # render_to_string의 반환값 설정
        mock_render_to_string.side_effect = [
            "<div>Weekly Trend HTML</div>",
            "<html><body>Final HTML</body></html>",
        ]

        result = weekly_trend_admin.render_full_preview(weekly_trend)

        # SafeString 타입인지 확인
        assert isinstance(result, SafeString)

        # iframe이 포함되어 있는지 확인
        assert "<iframe" in str(result)
        assert "srcdoc=" in str(result)

        # CSS 스타일이 포함되어 있는지 확인
        assert "<style>" in str(result)
        assert ".field-render_full_preview" in str(result)

        # render_to_string이 올바른 횟수로 호출되었는지 확인
        assert mock_render_to_string.call_count == 2

    def test_render_full_preview_no_insight(
        self, weekly_trend_admin, empty_insight_weekly_trend: WeeklyTrend
    ):
        """render_full_preview 메소드 테스트 (인사이트 없음)"""
        result = weekly_trend_admin.render_full_preview(
            empty_insight_weekly_trend
        )
        assert result == "No insight data to preview."

    @patch("insight.admin.weekly_trend_admin.render_to_string")
    def test_render_full_preview_exception(
        self,
        mock_render_to_string,
        weekly_trend_admin,
        weekly_trend: WeeklyTrend,
    ):
        """render_full_preview 메소드 테스트 (예외 발생)"""
        # render_to_string에서 예외 발생하도록 설정
        mock_render_to_string.side_effect = Exception("Template error")

        result = weekly_trend_admin.render_full_preview(weekly_trend)
        assert "Error rendering preview: Template error" in result

    def test_formatted_insight_json_with_data(
        self, weekly_trend_admin, weekly_trend: WeeklyTrend
    ):
        """formatted_insight_json 메소드 테스트 (데이터 있음)"""
        result = weekly_trend_admin.formatted_insight_json(weekly_trend)

        # SafeString 타입인지 확인
        assert isinstance(result, SafeString)

        # HTML 구조 확인
        assert "<pre><code>" in str(result)
        assert "</code></pre>" in str(result)

        # JSON 데이터가 포함되어 있는지 확인
        assert "trending_summary" in str(result)

    def test_formatted_insight_json_no_data(
        self, weekly_trend_admin, empty_insight_weekly_trend: WeeklyTrend
    ):
        """formatted_insight_json 메소드 테스트 (데이터 없음)"""
        result = weekly_trend_admin.formatted_insight_json(
            empty_insight_weekly_trend
        )
        assert result == "-"

    def test_mark_as_processed(
        self,
        weekly_trend_admin,
        weekly_trend: WeeklyTrend,
        request_factory,
    ):
        """mark_as_processed 액션 테스트"""
        # 초기 상태 설정
        weekly_trend.is_processed = False
        weekly_trend.processed_at = None
        weekly_trend.save()

        # QuerySet 생성
        queryset = WeeklyTrend.objects.filter(pk=weekly_trend.pk)

        # mark_as_processed 실행
        weekly_trend_admin.mark_as_processed(request_factory, queryset)

        # 결과 확인
        weekly_trend.refresh_from_db()
        assert weekly_trend.is_processed is True
        assert weekly_trend.processed_at is not None

        # message_user가 호출되었는지 확인 (실제로는 _messages.add가 호출됨)
        request_factory._messages.add.assert_called_once()

    def test_mark_as_processed_multiple_objects(
        self,
        weekly_trend_admin,
        request_factory,
        db,
        sample_weekly_trend_insight,
    ):
        """mark_as_processed 액션 테스트 (여러 객체)"""
        from datetime import date

        # 다른 주간 범위로 WeeklyTrend 객체 생성 (unique 제약조건 피하기)
        week_start1 = date(2025, 8, 1)  # 다른 주차
        week_end1 = date(2025, 8, 7)
        week_start2 = date(2025, 8, 8)  # 또 다른 주차
        week_end2 = date(2025, 8, 14)

        trend1 = WeeklyTrend.objects.create(
            week_start_date=week_start1,
            week_end_date=week_end1,
            insight=sample_weekly_trend_insight.to_json_dict(),
            is_processed=False,
        )
        trend2 = WeeklyTrend.objects.create(
            week_start_date=week_start2,
            week_end_date=week_end2,
            insight=sample_weekly_trend_insight.to_json_dict(),
            is_processed=False,
        )

        # QuerySet 생성
        queryset = WeeklyTrend.objects.filter(pk__in=[trend1.pk, trend2.pk])

        # mark_as_processed 실행
        weekly_trend_admin.mark_as_processed(request_factory, queryset)

        # 결과 확인
        trend1.refresh_from_db()
        trend2.refresh_from_db()

        assert trend1.is_processed is True
        assert trend1.processed_at is not None
        assert trend2.is_processed is True
        assert trend2.processed_at is not None

        # message_user가 호출되었는지 확인 (실제로는 _messages.add가 호출됨)
        request_factory._messages.add.assert_called_once()

    def test_admin_configuration(self, weekly_trend_admin):
        """Admin 클래스 설정 테스트"""
        # list_display 확인
        expected_list_display = (
            "id",
            "week_range",
            "summarize_insight",
            "is_processed_colored",
            "processed_at_formatted",
            "created_at",
        )
        assert weekly_trend_admin.list_display == expected_list_display

        # list_filter 확인
        expected_list_filter = ("is_processed", "week_start_date")
        assert weekly_trend_admin.list_filter == expected_list_filter

        # search_fields 확인
        expected_search_fields = ("insight",)
        assert weekly_trend_admin.search_fields == expected_search_fields

        # readonly_fields 확인
        expected_readonly_fields = (
            "processed_at",
            "render_full_preview",
            "formatted_insight_json",
        )
        assert weekly_trend_admin.readonly_fields == expected_readonly_fields

        # actions 확인
        expected_actions = ["mark_as_processed"]
        assert weekly_trend_admin.actions == expected_actions

        # fieldsets 확인
        assert len(weekly_trend_admin.fieldsets) == 4
        assert weekly_trend_admin.fieldsets[0][0] == "기간 정보"
        assert weekly_trend_admin.fieldsets[1][0] == "뉴스레터 미리보기"
        assert weekly_trend_admin.fieldsets[2][0] == "원본 데이터 (JSON)"
        assert weekly_trend_admin.fieldsets[3][0] == "처리 상태"
