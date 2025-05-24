import json

from django.contrib import admin
from django.http import HttpRequest
from django.template.defaultfilters import truncatechars
from django.urls import reverse
from django.utils.html import format_html

from utils.utils import get_local_now

from .models import UserWeeklyTrend, WeeklyTrend


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

        html = '<div class="module aligned">'

        # 트렌드 분석 섹션
        if "trend_analysis" in obj.insight:
            trend = obj.insight["trend_analysis"]
            html += '<h2 style="margin-top: 10px;">트렌드 분석</h2>'
            html += '<div style="margin-left: 15px;">'

            # 핫 키워드 - 단순히 쉼표로 구분된 목록으로 표시
            if "hot_keywords" in trend:
                html += "<h3>핵심 키워드</h3>"
                keywords = trend.get("hot_keywords", [])
                if keywords:
                    html += f'<p><strong>{", ".join(keywords)}</strong></p>'
                else:
                    html += "<p>키워드 없음</p>"

            # 제목 트렌드
            if "title_trends" in trend:
                html += f'<h3>제목 트렌드</h3><p style="line-height: 1.5;">{trend["title_trends"]}</p>'

            # 콘텐츠 트렌드
            if "content_trends" in trend:
                html += f'<h3>콘텐츠 트렌드</h3><p style="line-height: 1.5;">{trend["content_trends"]}</p>'

            # 인사이트
            if "insights" in trend:
                html += f'<h3>인사이트</h3><p style="line-height: 1.5;">{trend["insights"]}</p>'

            html += "</div>"

        # 트렌딩 요약 섹션
        if "trending_summary" in obj.insight:
            # UserWeeklyTrend와 WeeklyTrend 구분
            summary_title = (
                "작성 게시글 요약" if hasattr(obj, "user") else "트렌딩 요약"
            )
            html += f'<h2 style="margin-top: 20px;">{summary_title}</h2>'
            summaries = obj.insight["trending_summary"]

            if not summaries:
                html += "<p>요약 데이터 없음</p>"
            else:
                for i, summary in enumerate(summaries):
                    html += '<div style="margin: 15px 0; padding-left: 15px; border-left: 3px solid #ddd;">'
                    html += f'<h3 style="margin-bottom: 5px;">{i+1}. {summary["title"]}</h3>'
                    html += f'<p style="line-height: 1.5; margin-bottom: 8px;">{summary["summary"]}</p>'

                    if "key_points" in summary and summary["key_points"]:
                        html += "<p><strong>핵심 포인트:</strong> "
                        html += ", ".join(summary["key_points"])
                        html += "</p>"

                    html += "</div>"

        html += "</div>"
        return format_html("{}", html)


@admin.register(WeeklyTrend)
class WeeklyTrendAdmin(admin.ModelAdmin, JsonPreviewMixin):
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

    @admin.display(description="주 기간")
    def week_range(self, obj: WeeklyTrend):
        """주 기간을 표시"""
        return format_html(
            "{} ~ {}",
            obj.week_start_date.strftime("%Y-%m-%d"),
            obj.week_end_date.strftime("%Y-%m-%d"),
        )

    @admin.display(description="인사이트 미리보기")
    def insight_preview(self, obj: WeeklyTrend):
        """인사이트 미리보기"""
        return self.get_json_preview(obj, "insight")

    @admin.display(description="처리 완료")
    def is_processed_colored(self, obj: WeeklyTrend):
        """처리 상태를 색상으로 표시"""
        if obj.is_processed:
            return format_html(
                "{}", '<span style="color: green; font-weight: bold;">✓</span>'
            )
        return format_html(
            "{}", '<span style="color: red; font-weight: bold;">✗</span>'
        )

    @admin.display(description="처리 완료 시간")
    def processed_at_formatted(self, obj: WeeklyTrend):
        """처리 완료 시간 포맷팅"""
        if obj.processed_at:
            return obj.processed_at.strftime("%Y-%m-%d %H:%M")
        return "-"

    @admin.action(description="선택된 항목을 처리 완료로 표시하기")
    def mark_as_processed(self, request: HttpRequest, queryset: WeeklyTrend):
        """선택된 항목을 처리 완료로 표시"""
        queryset.update(is_processed=True, processed_at=get_local_now())
        self.message_user(
            request,
            f"{queryset.count()}개의 트렌드가 처리 완료로 표시되었습니다.",
        )


@admin.register(UserWeeklyTrend)
class UserWeeklyTrendAdmin(admin.ModelAdmin, JsonPreviewMixin):
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
    search_fields = ("user__email", "insight")
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
            obj.user.email or f"사용자 {obj.user.id}",
        )

    @admin.display(description="주 기간")
    def week_range(self, obj: UserWeeklyTrend):
        """주 기간을 표시"""
        return format_html(
            "{} ~ {}",
            obj.week_start_date.strftime("%Y-%m-%d"),
            obj.week_end_date.strftime("%Y-%m-%d"),
        )

    @admin.display(description="인사이트 미리보기")
    def insight_preview(self, obj: UserWeeklyTrend):
        """인사이트 미리보기"""
        return self.get_json_preview(obj, "insight")

    @admin.display(description="처리 완료")
    def is_processed_colored(self, obj: UserWeeklyTrend):
        """처리 상태를 색상으로 표시"""
        if obj.is_processed:
            return format_html(
                "{}", '<span style="color: green; font-weight: bold;">✓</span>'
            )
        return format_html(
            "{}", '<span style="color: red; font-weight: bold;">✗</span>'
        )

    @admin.display(description="처리 완료 시간")
    def processed_at_formatted(self, obj: UserWeeklyTrend):
        """처리 완료 시간 포맷팅"""
        if obj.processed_at:
            return obj.processed_at.strftime("%Y-%m-%d %H:%M")
        return "-"

    @admin.action(description="선택된 항목을 처리 완료로 표시하기")
    def mark_as_processed(self, request, queryset):
        """선택된 항목을 처리 완료로 표시"""
        queryset.update(is_processed=True, processed_at=get_local_now())
        self.message_user(
            request,
            f"{queryset.count()}개의 사용자 인사이트가 처리 완료로 표시되었습니다.",
        )
