# poetry run pytest insight/tests/test_user_weekly_trend_admin.py -v
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest

from insight.models import UserWeeklyTrend, WeeklyTrend
from utils.utils import get_local_now, get_previous_week_range


@pytest.mark.django_db
class TestUserWeeklyTrendAdmin:
    """UserWeeklyTrendAdmin 테스트"""

    def test_list_display_configuration(self, user_weekly_trend_admin):
        """list_display 설정 테스트"""
        expected_list_display = (
            "id",
            "user_info",
            "week_range",
            "summarize_insight",
            "is_processed_colored",
            "processed_at_formatted",
            "created_at",
        )
        assert user_weekly_trend_admin.list_display == expected_list_display

    def test_list_filter_configuration(self, user_weekly_trend_admin):
        """list_filter 설정 테스트"""
        expected_list_filter = ("is_processed", "week_start_date")
        assert user_weekly_trend_admin.list_filter == expected_list_filter

    def test_search_fields_configuration(self, user_weekly_trend_admin):
        """search_fields 설정 테스트"""
        expected_search_fields = ("user__username", "insight")
        assert user_weekly_trend_admin.search_fields == expected_search_fields

    def test_readonly_fields_configuration(self, user_weekly_trend_admin):
        """readonly_fields 설정 테스트"""
        expected_readonly_fields = (
            "processed_at",
            "render_full_preview",
            "formatted_insight_json",
        )
        assert (
            user_weekly_trend_admin.readonly_fields == expected_readonly_fields
        )

    def test_raw_id_fields_configuration(self, user_weekly_trend_admin):
        """raw_id_fields 설정 테스트"""
        expected_raw_id_fields = ("user",)
        assert user_weekly_trend_admin.raw_id_fields == expected_raw_id_fields

    def test_fieldsets_configuration(self, user_weekly_trend_admin):
        """fieldsets 설정 테스트"""
        fieldsets = user_weekly_trend_admin.fieldsets
        assert len(fieldsets) == 4

    def test_actions_configuration(self, user_weekly_trend_admin):
        """actions 설정 테스트"""
        expected_actions = ["mark_as_processed"]
        assert user_weekly_trend_admin.actions == expected_actions

    def test_get_queryset_select_related(self, user_weekly_trend_admin):
        """get_queryset 메소드가 select_related('user')를 포함하는지 테스트"""
        request = HttpRequest()
        request.method = "GET"
        queryset = user_weekly_trend_admin.get_queryset(request)
        assert hasattr(queryset, "query")
        assert "user" in str(queryset.query.select_related)

    def test_user_info_with_user(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """user_info 메소드 테스트 (사용자 있음)"""
        result = user_weekly_trend_admin.user_info(user_weekly_trend)
        assert user_weekly_trend.user.username in result
        assert "href=" in result
        assert 'target="_blank"' in result

    def test_user_info_without_user(self, user_weekly_trend_admin):
        """user_info 메소드 테스트 (사용자 없음)"""
        # DB에 저장하지 않고 메모리상 객체만 생성, 현재는 Not Null 제약 조건 있음
        mock_obj = MagicMock()
        mock_obj.user = None

        result = user_weekly_trend_admin.user_info(mock_obj)
        assert result == "-"

    def test_user_info_with_user_no_username(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """user_info 메소드 테스트 (사용자명 없음)"""
        user_weekly_trend.user.username = None
        user_weekly_trend.user.save()
        result = user_weekly_trend_admin.user_info(user_weekly_trend)
        assert f"사용자 {user_weekly_trend.user.id}" in result
        assert "href=" in result

    def test_summarize_insight_with_valid_data(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """summarize_insight 메소드 테스트 (유효한 데이터)"""
        result = user_weekly_trend_admin.summarize_insight(user_weekly_trend)
        if user_weekly_trend.insight.get("user_weekly_stats"):
            assert "조회수:" in result
            assert "새글:" in result
        if user_weekly_trend.insight.get("trending_summary"):
            assert "신규글:" in result

    def test_summarize_insight_with_stats_only(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """summarize_insight 메소드 테스트 (통계만 있는 경우)"""
        user_weekly_trend.insight = {
            "user_weekly_stats": {"views": 250, "new_posts": 3}
        }
        user_weekly_trend.save()
        result = user_weekly_trend_admin.summarize_insight(user_weekly_trend)
        assert "조회수: 250" in result
        assert "새글: 3" in result
        assert "신규글:" not in result

    def test_summarize_insight_no_data(self, user_weekly_trend_admin):
        """summarize_insight 메소드 테스트 (데이터 없음)"""
        week_start, week_end = get_previous_week_range()
        user_weekly_trend = UserWeeklyTrend(
            week_start_date=week_start, week_end_date=week_end, insight=None
        )
        result = user_weekly_trend_admin.summarize_insight(user_weekly_trend)
        assert result == "데이터 없음"

    def test_summarize_insight_invalid_data_type(
        self, user_weekly_trend_admin
    ):
        """summarize_insight 메소드 테스트 (잘못된 데이터 타입)"""
        week_start, week_end = get_previous_week_range()
        user_weekly_trend = UserWeeklyTrend(
            week_start_date=week_start,
            week_end_date=week_end,
            insight="invalid_string_data",
        )
        result = user_weekly_trend_admin.summarize_insight(user_weekly_trend)
        assert result == "데이터 없음"

    def test_summarize_insight_empty_dict(self, user_weekly_trend_admin):
        """summarize_insight 메소드 테스트 (빈 딕셔너리)"""
        week_start, week_end = get_previous_week_range()
        user_weekly_trend = UserWeeklyTrend(
            week_start_date=week_start, week_end_date=week_end, insight={}
        )
        result = user_weekly_trend_admin.summarize_insight(user_weekly_trend)
        assert result == "요약 정보 없음"

    def test_summarize_insight_with_trending_summary_empty_title(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """summarize_insight 메소드 테스트 (trending_summary는 있지만 title이 빈 경우)"""
        user_weekly_trend.insight = {
            "user_weekly_stats": {"views": 100, "new_posts": 2},
            "trending_summary": [{"title": "", "summary": "내용만 있음"}],
        }
        user_weekly_trend.save()

        result = user_weekly_trend_admin.summarize_insight(user_weekly_trend)
        assert "조회수: 100" in result
        assert "새글: 2" in result
        assert "신규글:" not in result

    def test_summarize_insight_with_trending_summary_not_list(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """summarize_insight 메소드 테스트 (trending_summary가 리스트가 아닌 경우)"""
        user_weekly_trend.insight = {
            "user_weekly_stats": {"views": 100, "new_posts": 2},
            "trending_summary": "not a list",
        }
        user_weekly_trend.save()

        result = user_weekly_trend_admin.summarize_insight(user_weekly_trend)
        assert "조회수: 100" in result
        assert "새글: 2" in result
        assert "신규글:" not in result

    def test_render_full_preview_with_weekly_trend(
        self, user_weekly_trend_admin, user_weekly_trend, weekly_trend
    ):
        """render_full_preview 메소드 테스트 (WeeklyTrend 존재)"""
        weekly_trend.week_start_date = user_weekly_trend.week_start_date
        weekly_trend.week_end_date = user_weekly_trend.week_end_date
        weekly_trend.insight = {"trending_summary": [{"title": "주간 트렌드"}]}
        weekly_trend.save()

        with patch("django.template.loader.render_to_string") as mock_render:
            mock_render.return_value = "<div>Mocked HTML</div>"
            with patch("utils.utils.from_dict") as mock_from_dict:
                mock_insight = MagicMock()
                mock_insight.to_dict.return_value = {"mocked": "data"}
                mock_from_dict.return_value = mock_insight

                result = user_weekly_trend_admin.render_full_preview(
                    user_weekly_trend
                )
                assert "<iframe" in result
                assert "style=" in result
                assert "field-render_full_preview" in result
                assert "max-width: 1400px" in result

    def test_render_full_preview_without_weekly_trend(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """render_full_preview 메소드 테스트 (WeeklyTrend 없음)"""
        WeeklyTrend.objects.filter(
            week_start_date=user_weekly_trend.week_start_date,
            week_end_date=user_weekly_trend.week_end_date,
        ).delete()

        with patch("django.template.loader.render_to_string") as mock_render:
            mock_render.side_effect = [
                "<div>User Weekly Trend HTML</div>",
                "<div>Final HTML with warning</div>",
            ]
            with patch("utils.utils.from_dict") as mock_from_dict:
                mock_insight = MagicMock()
                mock_insight.to_dict.return_value = {"mocked": "data"}
                mock_from_dict.return_value = mock_insight

                result = user_weekly_trend_admin.render_full_preview(
                    user_weekly_trend
                )
                assert "<iframe" in result

    def test_render_full_preview_weekly_trend_without_insight(
        self, user_weekly_trend_admin, user_weekly_trend, weekly_trend
    ):
        """render_full_preview 메소드 테스트 (WeeklyTrend는 있지만 insight 없음)"""
        weekly_trend.week_start_date = user_weekly_trend.week_start_date
        weekly_trend.week_end_date = user_weekly_trend.week_end_date
        weekly_trend.insight = {}  # null 대신 빈 딕셔너리
        weekly_trend.save()

        with patch("django.template.loader.render_to_string") as mock_render:
            mock_render.side_effect = [
                "<div>User Weekly Trend HTML</div>",
                "<div>Final HTML</div>",
            ]
            with patch("utils.utils.from_dict") as mock_from_dict:
                mock_insight = MagicMock()
                mock_insight.to_dict.return_value = {"mocked": "data"}
                mock_from_dict.return_value = mock_insight

                result = user_weekly_trend_admin.render_full_preview(
                    user_weekly_trend
                )
                assert "<iframe" in result

    def test_render_full_preview_no_insight(self, user_weekly_trend_admin):
        """render_full_preview 메소드 테스트 (인사이트 없음)"""
        week_start, week_end = get_previous_week_range()
        user_weekly_trend = UserWeeklyTrend(
            week_start_date=week_start, week_end_date=week_end, insight=None
        )
        result = user_weekly_trend_admin.render_full_preview(user_weekly_trend)
        assert result == "No insight data to preview."

    def test_render_full_preview_exception_handling(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """render_full_preview 메소드 테스트 (예외 발생)"""
        with patch(
            "utils.utils.from_dict", side_effect=Exception("Test error")
        ):
            result = user_weekly_trend_admin.render_full_preview(
                user_weekly_trend
            )
            assert "Error rendering preview: Test error" in result

    def test_formatted_insight_json_with_data(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """formatted_insight_json 메소드 테스트 (데이터 있음)"""
        result = user_weekly_trend_admin.formatted_insight_json(
            user_weekly_trend
        )
        assert "<pre><code>" in result
        assert "</code></pre>" in result

    def test_formatted_insight_json_no_data(self, user_weekly_trend_admin):
        """formatted_insight_json 메소드 테스트 (데이터 없음)"""
        week_start, week_end = get_previous_week_range()
        user_weekly_trend = UserWeeklyTrend(
            week_start_date=week_start, week_end_date=week_end, insight=None
        )
        result = user_weekly_trend_admin.formatted_insight_json(
            user_weekly_trend
        )
        assert result == "-"

    def test_mark_as_processed(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """mark_as_processed 메소드 테스트"""
        user_weekly_trend.is_processed = False
        user_weekly_trend.processed_at = None
        user_weekly_trend.save()

        request = HttpRequest()
        request.method = "POST"
        request.user = MagicMock()

        with patch("utils.utils.get_local_now") as mock_now:
            mock_now.return_value = get_local_now()
            with patch.object(
                user_weekly_trend_admin, "message_user"
            ) as mock_message:
                user_weekly_trend_admin.mark_as_processed(
                    request,
                    UserWeeklyTrend.objects.filter(pk=user_weekly_trend.pk),
                )
                mock_message.assert_called_once()
                message_text = mock_message.call_args[0][1]
                assert "사용자 인사이트" in message_text
                assert "처리 완료로 표시되었습니다" in message_text

        user_weekly_trend.refresh_from_db()
        assert user_weekly_trend.is_processed is True
        assert user_weekly_trend.processed_at is not None

    def test_mark_as_processed_multiple_items(
        self, user_weekly_trend_admin, user_weekly_trend, user
    ):
        """mark_as_processed 메소드 테스트 (여러 항목)"""
        # 다른 주차로 생성하여 unique constraint 회피
        other_week_start, other_week_end = get_previous_week_range()
        other_week_start = other_week_start + timedelta(days=7)
        other_week_end = other_week_end + timedelta(days=7)

        user_weekly_trend_2 = UserWeeklyTrend.objects.create(
            user=user,
            week_start_date=other_week_start,
            week_end_date=other_week_end,
            insight={"test": "data2"},
            is_processed=False,
        )

        request = HttpRequest()
        request.method = "POST"
        request.user = MagicMock()

        with patch("utils.utils.get_local_now") as mock_now:
            mock_now.return_value = get_local_now()
            with patch.object(
                user_weekly_trend_admin, "message_user"
            ) as mock_message:
                queryset = UserWeeklyTrend.objects.filter(
                    pk__in=[user_weekly_trend.pk, user_weekly_trend_2.pk]
                )
                user_weekly_trend_admin.mark_as_processed(request, queryset)
                message_text = mock_message.call_args[0][1]
                assert "2개의 사용자 인사이트" in message_text

    def test_week_range(self, user_weekly_trend_admin, user_weekly_trend):
        """week_range 메소드 테스트 (BaseTrendAdminMixin에서 상속)"""
        result = user_weekly_trend_admin.week_range(user_weekly_trend)
        expected_format = f"{user_weekly_trend.week_start_date.strftime('%Y-%m-%d')} ~ {user_weekly_trend.week_end_date.strftime('%Y-%m-%d')}"
        assert expected_format in result

    def test_is_processed_colored_true(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """is_processed_colored 메소드 테스트 (처리 완료)"""
        user_weekly_trend.is_processed = True
        user_weekly_trend.save()
        result = user_weekly_trend_admin.is_processed_colored(
            user_weekly_trend
        )
        assert "green" in result
        assert "✓" in result

    def test_is_processed_colored_false(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """is_processed_colored 메소드 테스트 (미처리)"""
        user_weekly_trend.is_processed = False
        user_weekly_trend.save()
        result = user_weekly_trend_admin.is_processed_colored(
            user_weekly_trend
        )
        assert "red" in result
        assert "✗" in result

    def test_processed_at_formatted_with_date(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 있음)"""
        now = get_local_now()
        user_weekly_trend.processed_at = now
        user_weekly_trend.save()
        result = user_weekly_trend_admin.processed_at_formatted(
            user_weekly_trend
        )
        assert now.strftime("%Y-%m-%d %H:%M") == result

    def test_processed_at_formatted_no_date(
        self, user_weekly_trend_admin, user_weekly_trend
    ):
        """processed_at_formatted 메소드 테스트 (날짜 없음)"""
        user_weekly_trend.processed_at = None
        user_weekly_trend.save()
        result = user_weekly_trend_admin.processed_at_formatted(
            user_weekly_trend
        )
        assert result == "-"
