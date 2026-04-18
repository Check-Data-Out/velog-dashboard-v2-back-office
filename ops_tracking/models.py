"""StatsRefreshRequest — stats refresh 요청의 라이프사이클 추적.

"누가 / 언제 / 성공·실패했는지" 를 조회하기 위한 전용 테이블. 요청 당 1 행,
request_id (uuid4) unique. 상태 전이는 :class:`RequestLifecycleService` 가 담당.
"""

from django.db import models

from common.models import TimeStampedModel


class StatsRefreshRequestStatus(models.TextChoices):
    """허용 전이:
    QUEUED -> PROCESSING -> {SUCCESS, FAILED}
    FAILED -> PROCESSING (reclaim)
    FAILED -> DLQ (max reclaims 초과)
    """

    QUEUED = "QUEUED", "큐에 적재"
    PROCESSING = "PROCESSING", "처리 중"
    SUCCESS = "SUCCESS", "성공"
    FAILED = "FAILED", "실패 (재시도 중)"
    DLQ = "DLQ", "DLQ 이동 (재시도 포기)"


class StatsRefreshRequest(TimeStampedModel):
    request_id = models.UUIDField(
        unique=True, db_index=True, verbose_name="요청 ID"
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="stats_refresh_requests",
        verbose_name="대상 사용자",
    )
    requested_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_stats_refreshes",
        verbose_name="요청자",
    )
    status = models.CharField(
        max_length=16,
        choices=StatsRefreshRequestStatus.choices,
        default=StatsRefreshRequestStatus.QUEUED,
        db_index=True,
        verbose_name="상태",
    )
    retry_count = models.PositiveSmallIntegerField(
        default=0, verbose_name="retry 횟수"
    )
    reclaimed_count = models.PositiveSmallIntegerField(
        default=0, verbose_name="reclaim 횟수"
    )
    last_error = models.TextField(
        blank=True, default="", verbose_name="마지막 에러"
    )
    finished_at = models.DateTimeField(
        null=True, blank=True, verbose_name="완료 일시"
    )

    class Meta:
        verbose_name = "Stats Refresh 요청"
        verbose_name_plural = "Stats Refresh 요청 목록"
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.request_id} ({self.status})"
