from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from insight.admin import BaseTrendAdminMixin, JsonPreviewMixin
from insight.models import UserWeeklyTrend
from utils.utils import get_local_now


@admin.register(UserWeeklyTrend)
class UserWeeklyTrendAdmin(
    admin.ModelAdmin, JsonPreviewMixin, BaseTrendAdminMixin
):
    list_display = (
        "id",
        "user_info",
        "week_range",
        "insight_preview",
        "is_processed_colored",
        "processed_at_formatted",
        "created_at",
    )
    list_filter = ("is_processed", "week_start_date")
    search_fields = ("user__username", "insight")
    readonly_fields = (
        "processed_at",
        "formatted_insight",
    )
    raw_id_fields = ("user",)

    fieldsets = (
        (
            "사용자 정보",
            {
                "fields": ("user", "week_start_date", "week_end_date"),
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

    def get_queryset(self, request: HttpRequest):
        queryset = super().get_queryset(request)
        return queryset.select_related("user")

    @admin.display(description="사용자")
    def user_info(self, obj: UserWeeklyTrend):
        """사용자 정보를 표시"""
        if not obj.user:
            return "-"

        user_url = reverse("admin:users_user_change", args=[obj.user.id])
        return format_html(
            '<a href="{}" target="_blank">{}</a>',
            user_url,
            obj.user.username or f"사용자 {obj.user.id}",
        )

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
