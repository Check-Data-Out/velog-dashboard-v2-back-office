from html import escape

from django.contrib import admin
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from insight.admin.base_admin import BaseTrendAdminMixin
from insight.models import (
    UserWeeklyTrend,
    WeeklyTrend,
    WeeklyTrendInsight,
    WeeklyUserTrendInsight,
)
from utils.utils import from_dict


@admin.register(UserWeeklyTrend)
class UserWeeklyTrendAdmin(admin.ModelAdmin, BaseTrendAdminMixin):
    list_display = (
        "id",
        "user_info",
        "week_range",
        "summarize_insight",
        "is_processed_colored",
        "processed_at_formatted",
        "created_at",
    )
    list_filter = ("is_processed", "week_start_date")
    search_fields = ("user__username", "insight")
    readonly_fields = (
        "processed_at",
        "render_full_preview",
        "formatted_insight_json",
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
            "뉴스레터 미리보기",
            {
                "fields": ("render_full_preview",),
                "classes": ("wide",),
            },
        ),
        (
            "원본 데이터 (JSON)",
            {
                "fields": ("formatted_insight_json",),
                "classes": ("wide", "collapse"),
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

    @admin.display(description="인사이트 요약")
    def summarize_insight(self, obj: UserWeeklyTrend):
        if not isinstance(obj.insight, dict):
            return "데이터 없음"

        summary_parts = []
        stats = obj.insight.get("user_weekly_stats")
        if stats:
            summary_parts.append(
                f"조회수: {stats.get('views', 0)}, 새글: {stats.get('new_posts', 0)}"
            )

        summary = obj.insight.get("trending_summary", [])
        if summary and isinstance(summary, list) and summary[0].get("title"):
            summary_parts.append(f"신규글: {summary[0]['title'][:20]}...")

        return " | ".join(summary_parts) if summary_parts else "요약 정보 없음"

    @admin.display(description="뉴스레터 템플릿")
    def render_full_preview(self, obj: UserWeeklyTrend):
        if not obj.insight:
            return "No insight data to preview."
        try:
            # 공통 주간 트렌드 데이터 조회
            weekly_trend = WeeklyTrend.objects.filter(
                week_start_date=obj.week_start_date,
                week_end_date=obj.week_end_date,
            ).first()

            if not weekly_trend or not weekly_trend.insight:
                weekly_trend_html = "<p><strong>경고:</strong> 해당 주차의 공통 WeeklyTrend를 찾을 수 없거나 데이터가 없습니다.</p>"
            else:
                weekly_trend_insight = from_dict(
                    WeeklyTrendInsight, weekly_trend.insight
                )
                weekly_trend_html = render_to_string(
                    "insights/weekly_trend.html",
                    {"insight": weekly_trend_insight.to_dict()},
                )

            # 사용자 주간 트렌드 렌더링
            user_weekly_insight = from_dict(
                WeeklyUserTrendInsight, obj.insight
            )
            user_weekly_trend_html = render_to_string(
                "insights/user_weekly_trend.html",
                {
                    "user": {
                        "username": obj.user.username if obj.user else "N/A"
                    },
                    "insight": user_weekly_insight.to_dict(),
                },
            )

            # 최종 뉴스레터 렌더링
            final_html = render_to_string(
                "insights/index.html",
                {
                    "s_date": obj.week_start_date,
                    "e_date": obj.week_end_date,
                    "user": {
                        "username": obj.user.username if obj.user else "N/A",
                        "email": obj.user.email if obj.user else "N/A",
                    },
                    "is_expired_token_user": False,
                    "weekly_trend_html": weekly_trend_html,
                    "user_weekly_trend_html": user_weekly_trend_html,
                },
            )

            # Admin 페이지 너비 확장을 위한 CSS
            style = """
            <style>
            /* iframe을 감싸는 필드의 너비 확장 */
            .field-render_full_preview {
                width: 100% !important;
                max-width: none !important;
            }
            
            /* Django admin 전체 콘텐츠 영역 확장 */
            .app-insight.model-weeklytrend .form-row,
            .app-insight.model-weeklytrend .wide,
            .app-insight.model-weeklytrend #content-main {
                max-width: 1400px !important;
                width: 100% !important;
            }
            </style>
            """

            iframe = f"""
            <iframe 
                srcdoc="{escape(final_html)}" 
                style="width: 100%; min-width: 600px; height: 600px; border: 1px solid #ccc;"
            ></iframe>
            """

            return mark_safe(style + iframe)
        except Exception as e:
            return f"Error rendering preview: {e}"
