import json
from html import escape

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from insight.models import UserWeeklyTrend, WeeklyTrend
from utils.utils import get_local_now


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

    @admin.display(description="Insight JSON")
    def formatted_insight_json(self, obj: WeeklyTrend | UserWeeklyTrend):
        if not obj.insight:
            return "-"
        json_str = json.dumps(obj.insight, indent=2, ensure_ascii=False)
        return mark_safe(f"<pre><code>{escape(json_str)}</code></pre>")

    # ========================================================================
    # Actions
    # ========================================================================

    @admin.action(description="선택된 항목을 처리 완료로 표시하기")
    def mark_as_processed(
        self, request: HttpRequest, queryset: QuerySet[UserWeeklyTrend]
    ):
        """선택된 항목을 처리 완료로 표시"""
        queryset.update(is_processed=True, processed_at=get_local_now())
        self.message_user(
            request,
            f"{queryset.count()}개의 사용자 인사이트가 처리 완료로 표시되었습니다.",
        )
