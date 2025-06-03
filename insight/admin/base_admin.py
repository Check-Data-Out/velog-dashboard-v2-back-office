import json

from django.contrib import admin
from django.template.defaultfilters import truncatechars
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
        return mark_safe(html)
