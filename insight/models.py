from dataclasses import dataclass, field
from datetime import timedelta

from django.db import models, transaction

from common.models import SerializableMixin, TimeStampedModel
from users.models import User
from utils.utils import get_local_now, get_this_week_monday


@dataclass
class TrendingItem(SerializableMixin):
    title: str
    summary: str
    key_points: list[str]
    username: str
    thumbnail: str
    slug: str

    def get_post_url(self) -> str:
        return f"https://velog.io/@{self.username}/{self.slug}"


@dataclass
class TrendAnalysis(SerializableMixin):
    hot_keywords: list[str]
    title_trends: str
    content_trends: str
    insights: str


@dataclass
class WeeklyTrendInsight(SerializableMixin):
    trending_summary: list[TrendingItem] = field(default_factory=list)
    trend_analysis: TrendAnalysis | None = None


@dataclass
class WeeklyUserStats(SerializableMixin):
    posts: int  # 전체 게시글 수
    new_posts: int  # 게시글 증가 수
    views: int  # 조회수 증가 수
    likes: int  # 좋아요 수 증가 수


@dataclass
class WeeklyUserReminder(SerializableMixin):
    """해당하는 주에 작성한 글이 없는 경우"""

    title: str  # 마지막 작성한 글 title
    days_ago: int  # 마지막 작성한 글 작성일자


@dataclass
class WeeklyUserTrendInsight(WeeklyTrendInsight):
    user_weekly_stats: WeeklyUserStats | None = None
    user_weekly_reminder: WeeklyUserReminder | None = None


REVIEW_READY = "ready"
REVIEW_NEEDS = "needs_review"
REVIEW_APPROVED = "approved"
REVIEW_STATUS_CHOICES = [
    (REVIEW_READY, "검수 불필요"),
    (REVIEW_NEEDS, "검수 대기(발송 보류)"),
    (REVIEW_APPROVED, "검수 승인"),
]
# 발송 가능한 검수 상태 (보류=needs_review 는 제외)
SENDABLE_REVIEW_STATUSES = (REVIEW_READY, REVIEW_APPROVED)


# 배치 시작·완료 표시는 insight JSON 의 이 키 아래에 둔다
BATCH_STATE_KEY = "_batch"
BATCH_USER_ANALYSIS_STARTED = "user_analysis_started_at"
BATCH_USER_ANALYSIS_COMPLETED = "user_analysis_completed_at"
BATCH_NEWSLETTER_STARTED = "newsletter_started_at"


class WeekQuerySet(models.QuerySet):
    def this_week(self, now=None):
        """이번 주 행. 주 종료일이 이번 주 월요일 전날(일요일) 이후인 행"""
        last_sunday = get_this_week_monday(now) - timedelta(days=1)
        return self.filter(week_end_date__gte=last_sunday)


class WeeklyTrend(TimeStampedModel):
    """
    전체 velog 주간 트렌드 인사이트
    """

    week_start_date = models.DateField(verbose_name="주 시작일")
    week_end_date = models.DateField(verbose_name="주 종료일")

    # 인사이트 데이터 - "WeeklyTrendInsight" 를 따라야 함
    insight = models.JSONField(
        verbose_name="핵심 키워드",
        help_text="주간 트렌드에 대한 핵심 키워드 및 인사이트 데이터, schema 변동에 유연하게 대응하기 위해 JSONField 사용",
        default=dict,
    )

    # 상태 필드
    is_processed = models.BooleanField(
        default=False, verbose_name="처리 완료 여부"
    )
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="처리 완료 시간"
    )
    # 광고 필터 검수 상태 (is_processed 와 분리 — 보류가 신주 발송을 잠식하지 않도록)
    review_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default=REVIEW_READY,
        verbose_name="검수 상태",
    )

    objects = WeekQuerySet.as_manager()

    class Meta:
        verbose_name = "주간 트렌드"
        verbose_name_plural = "주간 트렌드 목록"
        unique_together = ["week_start_date", "week_end_date"]
        indexes = [
            models.Index(fields=["week_start_date"]),
            models.Index(fields=["is_processed"]),
        ]

    def __str__(self):
        return f"주간 트렌드 ({self.week_start_date} ~ {self.week_end_date})"

    def batch_value(self, key: str) -> str | None:
        """insight["_batch"][key] 값. 없으면 None"""
        return self.insight.get(BATCH_STATE_KEY, {}).get(key)

    def mark_batch(self, key: str) -> None:
        """insight["_batch"][key] 에 지금 시각을 남긴다. 다른 키는 그대로 둔다.

        행을 잠근(select_for_update) 트랜잭션 안에서 DB 의 현재 insight 를
        다시 읽고 key 만 바꿔 저장한다. 그래서 동시에 불린 mark_batch 끼리는
        서로의 표시를 지우지 않는다. 잠그지 않고 insight 전체를 저장하는
        코드(save() 등)와 겹치는 것까지 막지는 않는다.
        """
        with transaction.atomic():
            insight = (
                WeeklyTrend.objects.select_for_update()
                .values_list("insight", flat=True)
                .get(pk=self.pk)
            )
            insight[BATCH_STATE_KEY] = {
                **insight.get(BATCH_STATE_KEY, {}),
                key: get_local_now().isoformat(),
            }
            WeeklyTrend.objects.filter(pk=self.pk).update(insight=insight)
        self.insight = insight


class UserWeeklyTrend(TimeStampedModel):
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

    # 인사이트 데이터 - "WeeklyUserTrendInsight" 를 따라야 함
    insight = models.JSONField(
        verbose_name="핵심 키워드",
        help_text="주간 트렌드에 대한 핵심 키워드 및 인사이트 데이터, schema 변동에 유연하게 대응하기 위해 JSONField 사용",
        default=dict,
    )

    # 상태 필드
    is_processed = models.BooleanField(
        default=False, verbose_name="처리 완료 여부"
    )
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="처리 완료 시간"
    )

    objects = WeekQuerySet.as_manager()

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


LABEL_REJECTED = "rejected"
LABEL_APPROVED = "approved"
LABEL_ESCAPED = "escaped"
LABEL_DECISION_CHOICES = [
    (LABEL_REJECTED, "검수에서 제거"),
    (LABEL_APPROVED, "검수 승인"),
    (LABEL_ESCAPED, "통과 후 스팸 판명"),
]


class FilterLabel(TimeStampedModel):
    """광고 필터 사람 게이트 결정/escaped 판명 라벨.

    audit 추적과 플라이휠(렉시콘·참조셋 보강) 시드로 사용한다.
    """

    slug = models.CharField(max_length=500, verbose_name="글 slug")
    decision = models.CharField(
        max_length=20,
        choices=LABEL_DECISION_CHOICES,
        verbose_name="결정",
    )
    score = models.FloatField(default=0.0, verbose_name="필터 점수")
    reason = models.TextField(blank=True, default="", verbose_name="사유")
    decided_by = models.CharField(
        max_length=100, blank=True, default="", verbose_name="결정자"
    )

    class Meta:
        verbose_name = "광고 필터 라벨"
        verbose_name_plural = "광고 필터 라벨 목록"

    def __str__(self):
        return f"[{self.decision}] {self.slug}"
