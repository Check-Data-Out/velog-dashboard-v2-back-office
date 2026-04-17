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
        return obj  # type: ignore[no-any-return]

    def _transition(
        self,
        request_id: str,
        from_statuses,
        **update_fields,
    ) -> StatsRefreshRequest | None:
        """허용된 이전 상태일 때만 UPDATE. race-safe 상태 전이 (architect #1).

        from_statuses: StatsRefreshRequestStatus enum 또는 str 의 리스트.
        Django __in 은 enum/문자열 모두 수용.
        """
        updated = StatsRefreshRequest.objects.filter(
            request_id=request_id, status__in=from_statuses
        ).update(**update_fields)
        if updated == 0:
            # 행이 없거나 전이가 허용되지 않은 현재 상태
            try:
                current = StatsRefreshRequest.objects.get(
                    request_id=request_id
                )
                logger.warning(
                    "lifecycle: transition rejected",
                    extra={
                        "request_id": str(request_id),
                        "current_status": current.status,
                        "to": update_fields.get("status"),
                    },
                )
            except StatsRefreshRequest.DoesNotExist:
                logger.warning(
                    "lifecycle: row missing",
                    extra={"request_id": str(request_id)},
                )
            return None
        try:
            return StatsRefreshRequest.objects.get(request_id=request_id)  # type: ignore[no-any-return]
        except StatsRefreshRequest.DoesNotExist:
            return None

    def mark_processing(
        self,
        request_id: str,
        retry_count: int = 0,
        reclaimed_count: int = 0,
    ) -> StatsRefreshRequest | None:
        # QUEUED 또는 FAILED (reclaim 재시도) 에서만 PROCESSING 진입 허용
        return self._transition(
            request_id,
            from_statuses=[
                StatsRefreshRequestStatus.QUEUED,
                StatsRefreshRequestStatus.FAILED,
            ],
            status=StatsRefreshRequestStatus.PROCESSING,
            retry_count=retry_count,
            reclaimed_count=reclaimed_count,
        )

    def mark_success(
        self, request_id: str, retry_count: int = 0
    ) -> StatsRefreshRequest | None:
        return self._transition(
            request_id,
            from_statuses=[StatsRefreshRequestStatus.PROCESSING],
            status=StatsRefreshRequestStatus.SUCCESS,
            retry_count=retry_count,
            finished_at=timezone.now(),
        )

    def mark_failed(
        self, request_id: str, error: str, retry_count: int = 0
    ) -> StatsRefreshRequest | None:
        return self._transition(
            request_id,
            from_statuses=[StatsRefreshRequestStatus.PROCESSING],
            status=StatsRefreshRequestStatus.FAILED,
            retry_count=retry_count,
            last_error=_truncate(error),
        )

    def mark_dlq(
        self, request_id: str, error: str, reclaimed_count: int = 0
    ) -> StatsRefreshRequest | None:
        # FAILED (reclaim 재시도 한도 초과) 에서만 DLQ 진입 허용
        return self._transition(
            request_id,
            from_statuses=[StatsRefreshRequestStatus.FAILED],
            status=StatsRefreshRequestStatus.DLQ,
            reclaimed_count=reclaimed_count,
            last_error=_truncate(error),
            finished_at=timezone.now(),
        )

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
