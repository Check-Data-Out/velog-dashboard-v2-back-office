"""Processing 큐 stuck 메시지 복구.

설계 원칙:
- 단일 consumer 인스턴스 전제 → threading.Lock 만 사용 (분산 락 미사용).
- stale 판정 기준은 ``processingStartedAt`` (BLMOVE 직후 consumer 가 기록).
  pending 장기 대기 메시지가 BLMOVE 직후 즉시 stale 판정되는 race 를 방지.
- fallback: ``processingStartedAt`` 이 없으면 ``lastAttemptAt`` → ``enqueuedAt``.
"""

import logging
import threading
import time

from django.utils import dateparse

from consumer.envelope import ensure_envelope
from modules.redis.client import RedisQueueClient
from modules.redis.config import RedisConfig
from ops_tracking.services import RequestLifecycleService

logger = logging.getLogger("consumer")


class ProcessingReclaimer:
    """Processing 큐의 stuck 메시지를 주기적으로 pending/DLQ 로 복원."""

    def __init__(
        self,
        redis_client: RedisQueueClient,
        config: type[RedisConfig] | None = None,
        shutdown_event: threading.Event | None = None,
    ) -> None:
        self.redis_client = redis_client
        self.config = config or RedisConfig
        self.shutdown_event = shutdown_event or threading.Event()
        self._lock = threading.Lock()
        self._lifecycle = None  # 지연 바인딩 (Django ORM 의존 회피 가능)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _lifecycle_service(self):
        if self._lifecycle is None:
            self._lifecycle = RequestLifecycleService()
        return self._lifecycle

    def _parse_epoch(self, ts: str | None) -> float:
        if not ts:
            return 0.0
        try:
            dt = dateparse.parse_datetime(ts)
            if dt is None:
                return 0.0
            return float(dt.timestamp())
        except (ValueError, TypeError):
            return 0.0

    def _is_stale(self, msg: dict, now_epoch: float) -> bool:
        # 우선순위: processingStartedAt (BLMOVE 시점) → lastAttemptAt → enqueuedAt
        # 세 값 모두 없으면 판정 불가 → fresh 로 취급해 다음 주기로 미룸.
        ref = (
            msg.get("processingStartedAt")
            or msg.get("lastAttemptAt")
            or msg.get("enqueuedAt")
        )
        if not ref:
            return False
        started = self._parse_epoch(ref)
        if started == 0.0:
            return False
        return bool(
            (now_epoch - started) >= self.config.RECLAIM_VISIBILITY_TIMEOUT_SEC
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reclaim_once(self, now_epoch: float | None = None) -> dict:
        """processing 큐 전수 스캔하여 stale 메시지를 DLQ 또는 pending 으로 이동.

        Returns:
            {"reclaimed": n, "dlq": m, "fresh": k}
        """
        now_epoch = now_epoch if now_epoch is not None else time.time()
        counts = {"reclaimed": 0, "dlq": 0, "fresh": 0}
        processing_queue = self.config.QUEUE_STATS_REFRESH_PROCESSING

        with self._lock:
            entries = self.redis_client.get_messages(
                processing_queue, with_raw=True
            )
            for raw_str, parsed in entries:
                # get_messages(with_raw=True) 는 JSON 파싱 실패 시
                # {"_raw": ..., "_error": "JSONDecodeError"} 를 반환한다.
                if not isinstance(parsed, dict) or "_error" in parsed:
                    # LREM 성공 후에만 DLQ 이동 — race 시 중복 DLQ 방지.
                    removed = self.redis_client.remove_message(
                        processing_queue, raw_str
                    )
                    if removed == 0:
                        # 다른 주기가 이미 처리. skip.
                        continue
                    payload = (
                        parsed
                        if isinstance(parsed, dict)
                        else {"_raw": raw_str}
                    )
                    self.redis_client.push_to_failed(payload)
                    counts["dlq"] += 1
                    continue

                msg = ensure_envelope(parsed)
                if not self._is_stale(msg, now_epoch):
                    counts["fresh"] += 1
                    continue

                # stale 확정 → processing 에서 제거
                removed = self.redis_client.remove_message(
                    processing_queue, raw_str
                )
                if removed == 0:
                    logger.warning(
                        f"reclaim skipped (LREM missed) - requestId={msg.get('requestId')}"
                    )
                    continue

                # ensure_envelope 이미 통과한 메시지이므로 int 임이 보장됨.
                msg["reclaimedCount"] = msg["reclaimedCount"] + 1
                rid = msg.get("requestId")
                if msg["reclaimedCount"] > self.config.RECLAIM_MAX_RECLAIMS:
                    self.redis_client.push_to_failed(msg)
                    counts["dlq"] += 1
                    self._safe_lifecycle(
                        "mark_dlq",
                        request_id=msg["requestId"],
                        error="reclaim max exceeded",
                        reclaimed_count=msg["reclaimedCount"],
                    )
                    logger.warning(
                        f"reclaim moved to DLQ (max exceeded) - requestId={rid}, reclaimedCount={msg['reclaimedCount']}"
                    )
                else:
                    # DB 상태를 FAILED 로 전환해야 consumer 가 재소비 시
                    # mark_processing(FAILED→PROCESSING) 전이를 받을 수 있다.
                    self._safe_lifecycle(
                        "mark_failed",
                        request_id=msg["requestId"],
                        error="reclaimed: reclaimed",
                        retry_count=msg["retryCount"],
                    )
                    msg["retryCount"] = 0
                    self.redis_client.enqueue_message(msg)
                    counts["reclaimed"] += 1
                    logger.info(
                        f"reclaim returned to pending - requestId={rid}, reclaimedCount={msg['reclaimedCount']}"
                    )
        return counts

    def _safe_lifecycle(self, method: str, **kwargs) -> None:
        """lifecycle 호출 실패 시에도 reclaimer 본체는 계속 동작 (fail-open)."""
        try:
            getattr(self._lifecycle_service(), method)(**kwargs)
        except Exception as e:
            logger.warning(f"reclaim lifecycle.{method} failed: {e}")

    def loop(self) -> None:
        """daemon thread 진입점. shutdown_event 가 set 될 때까지 반복."""
        interval = self.config.RECLAIM_INTERVAL_SEC
        logger.info(f"Reclaimer loop started (interval={interval}s)")
        while not self.shutdown_event.is_set():
            try:
                self.reclaim_once()
            except Exception as e:
                logger.error(f"reclaim iteration failed: {e}")
            # shutdown 이 오면 즉시 종료, 아니면 interval 만큼 대기
            self.shutdown_event.wait(timeout=interval)
        logger.info("Reclaimer loop stopped")
