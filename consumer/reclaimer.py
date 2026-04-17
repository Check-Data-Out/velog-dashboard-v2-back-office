"""Processing 큐 stuck 메시지 복구 (Plan.md Phase 5 핵심 / F3).

설계 원칙:
- 단일 consumer 인스턴스 전제 → threading.Lock 만 사용 (분산 락 미사용)
- Lua script 는 "1건 단위 claim" 만 담당 — 전수 스캔은 Python 에서 호출 루프
- 현재 시각은 Python 에서 ARGV 로 전달 (클러스터 복제 안전)
- 메시지에 enqueuedAt 없으면 ensure_envelope 가 이미 보강했다는 전제
"""

import logging
import threading
import time

from django.utils import dateparse

from consumer.envelope import ensure_envelope
from modules.redis.client import RedisQueueClient
from modules.redis.config import RedisConfig

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
        """RequestLifecycleService 지연 import (circular 회피)."""
        if self._lifecycle is None:
            from ops_tracking.services import RequestLifecycleService

            self._lifecycle = RequestLifecycleService()
        return self._lifecycle

    def _parse_epoch(self, ts: str | None) -> float:
        if not ts:
            return 0.0
        try:
            dt = dateparse.parse_datetime(ts)
            if dt is None:
                return 0.0
            return dt.timestamp()
        except (ValueError, TypeError):
            return 0.0

    def _is_stale(self, msg: dict, now_epoch: float) -> bool:
        enqueued = self._parse_epoch(msg.get("enqueuedAt"))
        return (
            now_epoch - enqueued
        ) >= self.config.RECLAIM_VISIBILITY_TIMEOUT_SEC

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
                    self.redis_client.remove_message(processing_queue, raw_str)
                    self.redis_client.push_to_failed(
                        parsed
                        if isinstance(parsed, dict)
                        else {"_raw": raw_str}
                    )
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
                        "reclaim: LREM 원본 불일치 — 건너뜀",
                        extra={"requestId": msg.get("requestId")},
                    )
                    continue

                msg["reclaimedCount"] = int(msg.get("reclaimedCount", 0)) + 1
                if msg["reclaimedCount"] > self.config.RECLAIM_MAX_RECLAIMS:
                    self.redis_client.push_to_failed(msg)
                    counts["dlq"] += 1
                    self._safe_mark_dlq(msg)
                    logger.warning(
                        "reclaim: max 초과 → DLQ",
                        extra={
                            "requestId": msg.get("requestId"),
                            "reclaimedCount": msg["reclaimedCount"],
                        },
                    )
                else:
                    # retryCount 는 0 으로 리셋 (플랜 설계)
                    msg["retryCount"] = 0
                    self.redis_client.enqueue_message(msg)
                    counts["reclaimed"] += 1
                    logger.info(
                        "reclaim: pending 복귀",
                        extra={
                            "requestId": msg.get("requestId"),
                            "reclaimedCount": msg["reclaimedCount"],
                        },
                    )
        return counts

    def _safe_mark_dlq(self, msg: dict) -> None:
        """ops_tracking 실패해도 reclaimer 본체는 계속 동작."""
        try:
            self._lifecycle_service().mark_dlq(
                request_id=msg["requestId"],
                error="reclaim max exceeded",
                reclaimed_count=int(msg.get("reclaimedCount", 0)),
            )
        except Exception as e:
            logger.warning(f"reclaim mark_dlq failed: {e}")

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
