"""RequestLifecycleService — StatsRefreshRequest 상태 전이를 담당.

모든 mark_* 는 request_id 기반 update_or_create 로 idempotent 보장.
consumer 가 동일 메시지를 reclaim 재처리해도 행이 중복되지 않는다.
"""

import logging

from django.utils import timezone

from ops_tracking.models import StatsRefreshRequest, StatsRefreshRequestStatus

logger = logging.getLogger(__name__)

_LAST_ERROR_MAX_LEN = 2000


def _truncate(text: str, max_len: int = _LAST_ERROR_MAX_LEN) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len]


class RequestLifecycleService:
    """StatsRefreshRequest 의 상태 전이 API."""

    def mark_queued(
        self,
        request_id: str,
        user_id: int,
        requested_by: int | None = None,
    ) -> StatsRefreshRequest:
        obj, created = StatsRefreshRequest.objects.update_or_create(
            request_id=request_id,
            defaults={
                "user_id": user_id,
                "requested_by_id": requested_by,
                "status": StatsRefreshRequestStatus.QUEUED,
                "finished_at": None,
            },
        )
        logger.info(
            "lifecycle: mark_queued",
            extra={"request_id": str(request_id), "created": created},
        )
        return obj

    def mark_processing(
        self,
        request_id: str,
        retry_count: int = 0,
        reclaimed_count: int = 0,
    ) -> StatsRefreshRequest | None:
        updated = StatsRefreshRequest.objects.filter(
            request_id=request_id
        ).update(
            status=StatsRefreshRequestStatus.PROCESSING,
            retry_count=retry_count,
            reclaimed_count=reclaimed_count,
        )
        if updated == 0:
            logger.warning(
                "lifecycle: mark_processing found no row",
                extra={"request_id": str(request_id)},
            )
            return None
        return StatsRefreshRequest.objects.get(request_id=request_id)

    def mark_success(
        self, request_id: str, retry_count: int = 0
    ) -> StatsRefreshRequest | None:
        updated = StatsRefreshRequest.objects.filter(
            request_id=request_id
        ).update(
            status=StatsRefreshRequestStatus.SUCCESS,
            retry_count=retry_count,
            finished_at=timezone.now(),
        )
        if updated == 0:
            return None
        return StatsRefreshRequest.objects.get(request_id=request_id)

    def mark_failed(
        self, request_id: str, error: str, retry_count: int = 0
    ) -> StatsRefreshRequest | None:
        updated = StatsRefreshRequest.objects.filter(
            request_id=request_id
        ).update(
            status=StatsRefreshRequestStatus.FAILED,
            retry_count=retry_count,
            last_error=_truncate(error),
        )
        if updated == 0:
            return None
        return StatsRefreshRequest.objects.get(request_id=request_id)

    def mark_dlq(
        self, request_id: str, error: str, reclaimed_count: int = 0
    ) -> StatsRefreshRequest | None:
        updated = StatsRefreshRequest.objects.filter(
            request_id=request_id
        ).update(
            status=StatsRefreshRequestStatus.DLQ,
            reclaimed_count=reclaimed_count,
            last_error=_truncate(error),
            finished_at=timezone.now(),
        )
        if updated == 0:
            return None
        return StatsRefreshRequest.objects.get(request_id=request_id)

    def has_inflight_for_users(self, user_ids: list[int]) -> set[int]:
        """QUEUED 또는 PROCESSING 상태로 이미 진행 중인 user_id 집합 반환."""
        if not user_ids:
            return set()
        return set(
            StatsRefreshRequest.objects.filter(
                user_id__in=user_ids,
                status__in=[
                    StatsRefreshRequestStatus.QUEUED,
                    StatsRefreshRequestStatus.PROCESSING,
                ],
            ).values_list("user_id", flat=True)
        )
