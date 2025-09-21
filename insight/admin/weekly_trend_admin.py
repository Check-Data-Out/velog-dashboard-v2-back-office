from html import escape

from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from insight.admin.base_admin import BaseTrendAdminMixin
from insight.models import WeeklyTrend, WeeklyTrendInsight
from utils.utils import from_dict


@admin.register(WeeklyTrend)
class WeeklyTrendAdmin(admin.ModelAdmin, BaseTrendAdminMixin):
    list_display = (
        "id",
        "week_range",
        "summarize_insight",
        "is_processed_colored",
        "processed_at_formatted",
        "created_at",
    )
    list_filter = ("is_processed", "week_start_date")
    search_fields = ("insight",)
    readonly_fields = (
        "processed_at",
        "render_full_preview",
        "formatted_insight_json",
    )
    fieldsets = (
        (
            "기간 정보",
            {
                "fields": ("week_start_date", "week_end_date"),
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

    @admin.display(description="인사이트 요약")
    def summarize_insight(self, obj: WeeklyTrend):
        if not isinstance(obj.insight, dict):
            return "데이터 없음"

        summary_parts = []
        summary_count = len(obj.insight.get("trending_summary", []))
        summary_parts.append(f"요약: {summary_count}개")

        keywords = obj.insight.get("trend_analysis", {}).get(
            "hot_keywords", []
        )
        if keywords:
            summary_parts.append(f"키워드: {', '.join(keywords[:2])}...")

        return " | ".join(summary_parts) if summary_parts else "요약 정보 없음"

    @admin.display(description="뉴스레터 템플릿")
    def render_full_preview(self, obj: WeeklyTrend):
        if not obj.insight:
            return "No insight data to preview."
        try:
            weekly_trend_insight = from_dict(WeeklyTrendInsight, obj.insight)
            context = {"insight": weekly_trend_insight.to_dict()}
            weekly_trend_html = render_to_string(
                "insights/weekly_trend.html", context
            )

            final_html = render_to_string(
                "insights/index.html",
                {
                    "s_date": obj.week_start_date,
                    "e_date": obj.week_end_date,
                    "is_expired_token_user": False,
                    "weekly_trend_html": weekly_trend_html,
                    "user_weekly_trend_html": None,
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
