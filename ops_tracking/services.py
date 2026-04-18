"""RequestLifecycleService — StatsRefreshRequest 상태 전이를 담당.

모든 mark_* 는 request_id 기반 update_or_create 로 idempotent 보장.
consumer 가 동일 메시지를 reclaim 재처리해도 행이 중복되지 않는다.
"""

import logging

from django.db import transaction
from django.utils import timezone

from ops_tracking.models import StatsRefreshRequest, StatsRefreshRequestStatus

logger = logging.getLogger(__name__)

LAST_ERROR_MAX_LEN = 2000

# terminal 상태 — 이 상태의 요청은 mark_queued 로 되돌릴 수 없다.
TERMINAL_STATUSES = (
    StatsRefreshRequestStatus.SUCCESS,
    StatsRefreshRequestStatus.DLQ,
)


def _truncate(text: str, max_len: int = LAST_ERROR_MAX_LEN) -> str:
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
        """QUEUED 로 마킹. terminal(SUCCESS/DLQ) 행은 덮어쓰지 않는다.

        외부 producer 가 같은 request_id 를 재전송하거나 admin 이 실수로 같은
        UUID 를 두 번 넣는 상황에서 SUCCESS/DLQ 를 inflight 로 되돌리면 감사성이
        깨지므로, 기존 terminal 행은 그대로 두고 경고만 남긴다.
        """
        with transaction.atomic():
            existing = (
                StatsRefreshRequest.objects.select_for_update()
                .filter(request_id=request_id)
                .first()
            )
            if existing and existing.status in TERMINAL_STATUSES:
                logger.warning(
                    f"mark_queued skipped (terminal status={existing.status}) "
                    f"request_id={request_id}"
                )
                return existing  # type: ignore[no-any-return]
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
            f"lifecycle.mark_queued (created={created}) request_id={request_id}"
        )
        return obj  # type: ignore[no-any-return]

    def try_mark_queued_if_no_inflight(
        self,
        request_id: str,
        user_id: int,
        requested_by: int | None = None,
    ) -> StatsRefreshRequest | None:
        """동일 user 에 inflight(QUEUED/PROCESSING) 가 없을 때만 QUEUED 생성.

        user_id 단위 원자적 중복 가드. admin 경로에서 같은 사용자 동시 요청이
        서로 다른 request_id 로 각각 통과하는 race 를 차단한다.
        """
        with transaction.atomic():
            inflight = (
                StatsRefreshRequest.objects.select_for_update()
                .filter(
                    user_id=user_id,
                    status__in=[
                        StatsRefreshRequestStatus.QUEUED,
                        StatsRefreshRequestStatus.PROCESSING,
                    ],
                )
                .exists()
            )
            if inflight:
                return None
            obj = StatsRefreshRequest.objects.create(
                request_id=request_id,
                user_id=user_id,
                requested_by_id=requested_by,
                status=StatsRefreshRequestStatus.QUEUED,
            )
        return obj  # type: ignore[no-any-return]

    def _transition(
        self,
        request_id: str,
        from_statuses,
        **update_fields,
    ) -> StatsRefreshRequest | None:
        """허용된 이전 상태일 때만 UPDATE. race-safe 상태 전이.

        QuerySet.update() 는 auto_now 를 실행하지 않으므로 updated_at 을 명시.
        """
        update_fields.setdefault("updated_at", timezone.now())
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
                    f"lifecycle transition rejected - request_id={request_id}, "
                    f"current={current.status}, to={update_fields.get('status')}"
                )
            except StatsRefreshRequest.DoesNotExist:
                logger.warning(
                    f"lifecycle row missing - request_id={request_id}"
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
        # FAILED (재시도 한도 초과) 또는 PROCESSING (reclaim 중 직접 DLQ) 에서 진입 허용
        return self._transition(
            request_id,
            from_statuses=[
                StatsRefreshRequestStatus.FAILED,
                StatsRefreshRequestStatus.PROCESSING,
            ],
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
