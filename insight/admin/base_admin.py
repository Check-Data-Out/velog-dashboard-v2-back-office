import json

from django.contrib import admin
from django.template.defaultfilters import truncatechars
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from insight.models import UserWeeklyTrend, WeeklyTrend


class BaseTrendAdminMixin:
    """공통된 트렌드 관련 필드를 표시하기 위한 Mixin"""

    @admin.display(description="주 기간")
    def week_range(self, obj: WeeklyTrend | UserWeeklyTrend):
        """주 기간을 표시"""
        return format_html(
            "{} ~ {}",
            obj.week_start_date.strftime("%Y-%m-%d"),
            obj.week_end_date.strftime("%Y-%m-%d"),
        )

    @admin.display(description="인사이트 미리보기")
    def insight_preview(self, obj: WeeklyTrend | UserWeeklyTrend):
        """인사이트 미리보기"""
        return self.get_json_preview(obj, "insight")

    @admin.display(description="처리 완료")
    def is_processed_colored(self, obj: WeeklyTrend | UserWeeklyTrend):
        """처리 상태를 색상으로 표시"""
        if obj.is_processed:
            return format_html(
                '<span style="color: green; font-weight: bold;">{}</span>', "✓"
            )
        return format_html(
            '<span style="color: red; font-weight: bold;">{}</span>', "✗"
        )

    @admin.display(description="처리 완료 시간")
    def processed_at_formatted(self, obj: WeeklyTrend | UserWeeklyTrend):
        """처리 완료 시간 포맷팅"""
        if obj.processed_at:
            return obj.processed_at.strftime("%Y-%m-%d %H:%M")
        return "-"


class JsonPreviewMixin:
    """JSONField를 보기 좋게 표시하기 위한 Mixin"""

    def get_json_preview(
        self, obj: WeeklyTrend | UserWeeklyTrend, field_name, max_length=150
    ):
        """JSONField 내용의 미리보기를 반환"""
        json_data = getattr(obj, field_name, {})
        if not json_data:
            return "-"

        # JSON 문자열로 변환하여 일부만 표시
        json_str = json.dumps(json_data, ensure_ascii=False)
        return truncatechars(json_str, max_length)

    @admin.display(description="인사이트 데이터")
    def formatted_insight(self, obj: WeeklyTrend | UserWeeklyTrend):
        """인사이트 JSON을 보기 좋게 포맷팅하여 표시"""
        if not hasattr(obj, "insight") or not obj.insight:
            return "-"

        context = {"insight": obj.insight, "user": getattr(obj, "user", None)}
        # render_to_string을 사용하여 템플릿 렌더링
        html = render_to_string("insights/insight_preview.html", context)
        return mark_safe(html)
