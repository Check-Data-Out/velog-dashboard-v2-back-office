# insights/models.py
from django.db import models

from common.models import TimeStampedModel
from users.models import User


class WeeklyTrend(TimeStampedModel):
    """
    전체 velog 주간 트렌드 인사이트
    """

    week_start_date = models.DateField(verbose_name="주 시작일")
    week_end_date = models.DateField(verbose_name="주 종료일")

    # 인사이트 데이터
    insight = models.JSONField(
        verbose_name="핵심 키워드",
        help_text="주간 트렌드에 대한 핵심 키워드 및 인사이트 데이터, schema 변동에 유연하게 대응하기 위해 JSONField 사용",
        default=dict,
    )
    # content_summary = models.TextField(verbose_name="세부 내용 요약")
    # title_trends = models.JSONField(verbose_name="제목 트렌드", default=dict)
    # overall_trend_analysis = models.TextField(verbose_name="전체 트렌드 분석")

    # 상태 필드
    is_processed = models.BooleanField(
        default=False, verbose_name="처리 완료 여부"
    )
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="처리 완료 시간"
    )

    class Meta:
        verbose_name = "주간 트렌드"
        verbose_name_plural = "주간 트렌드 목록"
        unique_together = ["week_start_date", "week_end_date"]
        indexes = [
            models.Index(fields=["week_start_date"]),
            models.Index(fields=["is_processed"]),
            models.Index(fields=["is_sent"]),
        ]

    def __str__(self):
        return f"주간 트렌드 ({self.week_start_date} ~ {self.week_end_date})"


class UserWeeklyInsight(TimeStampedModel):
    """
    사용자별 주간 게시글 인사이트
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="weekly_insights",
        verbose_name="사용자",
    )
    week_start_date = models.DateField(verbose_name="주 시작일")
    week_end_date = models.DateField(verbose_name="주 종료일")

    # 인사이트 데이터
    insight = models.JSONField(
        verbose_name="핵심 키워드",
        help_text="주간 트렌드에 대한 핵심 키워드 및 인사이트 데이터, schema 변동에 유연하게 대응하기 위해 JSONField 사용",
        default=dict,
    )
    # view_count_changes = models.JSONField(verbose_name="조회수 변동", default=dict)
    # key_keywords = models.JSONField(verbose_name="핵심 키워드", default=dict)
    # content_summary = models.TextField(verbose_name="세부 내용 요약")
    # overall_trend_analysis = models.TextField(verbose_name="전체 트렌드 분석")

    # 상태 필드
    is_processed = models.BooleanField(
        default=False, verbose_name="처리 완료 여부"
    )
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="처리 완료 시간"
    )

    class Meta:
        verbose_name = "사용자 주간 인사이트"
        verbose_name_plural = "사용자 주간 인사이트 목록"
        unique_together = ["user", "week_start_date", "week_end_date"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["week_start_date"]),
            models.Index(fields=["is_processed"]),
        ]

    def __str__(self):
        return f"{self.user.email} 주간 인사이트 ({self.week_start_date} ~ {self.week_end_date})"
