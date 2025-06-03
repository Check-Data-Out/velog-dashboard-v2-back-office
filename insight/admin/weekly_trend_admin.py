from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from insight.admin import BaseTrendAdminMixin, JsonPreviewMixin
from insight.models import WeeklyTrend
from utils.utils import get_local_now


@admin.register(WeeklyTrend)
class WeeklyTrendAdmin(
    admin.ModelAdmin, JsonPreviewMixin, BaseTrendAdminMixin
):
    list_display = (
        "id",
        "week_range",
        "insight_preview",
        "is_processed_colored",
        "processed_at_formatted",
        "created_at",
    )
    list_filter = ("is_processed", "week_start_date")
    search_fields = ("insight",)
    readonly_fields = ("processed_at", "formatted_insight")
    fieldsets = (
        (
            "기간 정보",
            {
                "fields": ("week_start_date", "week_end_date"),
            },
        ),
        (
            "인사이트 데이터",
            {
                "fields": ("formatted_insight",),
                "classes": ("wide", "extrapretty"),
            },
        ),
        (
            "처리 상태",
            {
                "fields": ("is_processed", "processed_at"),
            },
        ),
    )

    actions = ["mark_as_processed"]

    @admin.action(description="선택된 항목을 처리 완료로 표시하기")
    def mark_as_processed(
        self, request: HttpRequest, queryset: QuerySet[WeeklyTrend]
    ):
        """선택된 항목을 처리 완료로 표시"""
        queryset.update(is_processed=True, processed_at=get_local_now())
        self.message_user(
            request,
            f"{queryset.count()}개의 트렌드가 처리 완료로 표시되었습니다.",
        )
