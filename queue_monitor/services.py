"""Queue Monitor 서비스 레이어.

조율이 필요한 메서드만 둔다:
  - enqueue_stats_refresh : envelope 생성 + push + 중복 요청 가드
  - retry_failed_message  : DLQ -> pending 이동 + retryCount 리셋
  - purge_failed          : DLQ 전량 삭제

단순 조회 (큐 크기, DLQ 목록 읽기) 는 admin 이 RedisQueueClient 를 직접 호출한다.
"""

import logging

from consumer.envelope import build_envelope
from modules.redis.client import RedisQueueClient, get_redis_client
from modules.redis.config import RedisConfig

logger = logging.getLogger(__name__)


class QueueMonitorService:
    """큐 운영 조율 로직 (admin 과 reclaimer 공용)."""

    def __init__(
        self,
        redis_client: RedisQueueClient | None = None,
        config: type[RedisConfig] | None = None,
    ) -> None:
        self.redis_client = redis_client or get_redis_client()
        self.config = config or RedisConfig

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue_stats_refresh(
        self,
        user_ids: list[int],
        requested_by: int | None = None,
        skip_user_ids: set[int] | None = None,
    ) -> tuple[int, int]:
        """여러 user_id 에 대해 envelope 을 만들고 pending 큐에 push.

        Returns:
            (queued, skipped) 튜플. skip_user_ids 로 전달된 id 는 pending 하지 않음.
        """
        skip = skip_user_ids or set()
        queued = 0
        skipped = 0
        for user_id in user_ids:
            if user_id in skip:
                skipped += 1
                continue
            envelope = build_envelope(
                user_id=user_id, requested_by=requested_by
            )
            self.redis_client.enqueue_message(envelope)
            queued += 1
        return queued, skipped

    # ------------------------------------------------------------------
    # DLQ operations
    # ------------------------------------------------------------------

    def retry_failed_message(self, request_id: str) -> bool:
        """DLQ 에서 requestId 일치 메시지 1건을 찾아 pending 으로 복귀.

        retryCount 는 0 으로 리셋. reclaimedCount 는 유지 (poison pill 방어).
        LREM 은 반드시 **원본 raw 문자열** 로 호출해야 Redis 저장값과 정확 일치.

        실패 복구: LREM 성공 후 enqueue 실패 시 best-effort 로 DLQ 에 재삽입해
        데이터 유실을 방지한다 (완전 원자화는 Lua/transaction 이 필요하지만
        본 플랜은 과한 추상화를 지양 — 본 분기가 튈 확률은 Redis 장애 시점에 한정).
        """
        failed_queue = self.config.QUEUE_STATS_REFRESH_FAILED
        for raw_str, msg in self.redis_client.get_messages(
            failed_queue, with_raw=True
        ):
            if not isinstance(msg, dict) or msg.get("requestId") != request_id:
                continue
            removed = self.redis_client.remove_message(failed_queue, raw_str)
            if removed == 0:
                logger.warning(
                    f"retry_failed_message: DLQ 원본 제거 실패 (requestId={request_id})"
                )
                return False
            msg["retryCount"] = 0
            msg["lastAttemptAt"] = None
            try:
                self.redis_client.enqueue_message(msg)
            except Exception as e:
                logger.error(
                    f"retry_failed_message: pending enqueue 실패 — DLQ 에 복구 시도 ({request_id}): {e}"
                )
                try:
                    self.redis_client.push_to_failed(msg)
                except Exception as restore_err:
                    logger.error(
                        f"retry_failed_message: DLQ 복구도 실패 ({request_id}): {restore_err}"
                    )
                return False
            logger.info(
                f"retry_failed_message: pending 복귀 완료 ({request_id})"
            )
            return True
        logger.warning(
            f"retry_failed_message: DLQ 에서 requestId={request_id} 미발견"
        )
        return False

    def purge_failed(self) -> int:
        """DLQ 전량 삭제. 삭제 직전 크기를 반환 (감사 로그)."""
        return self.redis_client.flush_queue(
            self.config.QUEUE_STATS_REFRESH_FAILED
        )

    # ------------------------------------------------------------------
    # Read helpers (admin 뷰가 직접 호출)
    # ------------------------------------------------------------------

    def get_queue_stats(self) -> dict[str, int]:
        """3개 큐 크기 반환."""
        return {
            "pending": self.redis_client.get_queue_size(
                self.config.QUEUE_STATS_REFRESH
            ),
            "processing": self.redis_client.get_queue_size(
                self.config.QUEUE_STATS_REFRESH_PROCESSING
            ),
            "failed": self.redis_client.get_queue_size(
                self.config.QUEUE_STATS_REFRESH_FAILED
            ),
        }

    def get_failed_messages(
        self, offset: int = 0, limit: int = 50
    ) -> list[dict]:
        """DLQ 페이지네이션 조회."""
        end = offset + limit - 1
        return self.redis_client.get_messages(
            self.config.QUEUE_STATS_REFRESH_FAILED, offset, end
        )
