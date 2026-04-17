import logging
import signal
import sys
import threading
import time

import sentry_sdk
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

# Django setup must be imported first
import consumer.setup_django  # noqa: F401
from consumer.config import ConsumerConfig, RedisConfig
from consumer.envelope import ensure_envelope
from consumer.healthz import start_healthz_server
from consumer.message_handler import MessageProcessor
from consumer.reclaimer import ProcessingReclaimer
from consumer.shutdown import get_shutdown_event
from modules.redis.client import (
    RedisQueueClient,
    get_redis_client,
    reset_redis_client,
)

logger = logging.getLogger("consumer")


class StatsRefreshConsumer:
    """Main consumer process for stats refresh queue."""

    def __init__(
        self,
        redis_client: RedisQueueClient | None = None,
        redis_config: type[RedisConfig] | None = None,
        consumer_config: type[ConsumerConfig] | None = None,
    ) -> None:
        """Initialize consumer.

        Args:
            redis_client: RedisQueueClient 인스턴스 (DI 지원, 기본값: 싱글톤)
            redis_config: RedisConfig 클래스 (DI 지원, 기본값: RedisConfig)
            consumer_config: ConsumerConfig 클래스 (DI 지원, 기본값: ConsumerConfig)
        """
        self._injected_redis_client = redis_client
        self.redis_client: RedisQueueClient | None = None
        self.redis_config = redis_config or RedisConfig
        self.consumer_config = consumer_config or ConsumerConfig
        self.message_processor = MessageProcessor(config=self.redis_config)
        self.running = False
        self.processing_message = False
        self._reclaimer_thread: threading.Thread | None = None
        self._lifecycle = None  # 지연 import

        # Statistics
        self.stats = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "start_time": time.time(),
            "last_heartbeat_at": time.time(),
            "last_message_at": None,
        }

        # Setup signal handlers
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum: int, frame) -> None:
        """Handle shutdown signals.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        logger.info(
            f"Received {signal_name} signal, initiating graceful shutdown..."
        )
        self.shutdown()

    def start(self) -> None:
        """Start the consumer process."""
        logger.info(f"Starting {self.consumer_config.PROCESS_NAME}...")

        try:
            # Initialize Redis client (DI 또는 싱글톤)
            self.redis_client = (
                self._injected_redis_client or get_redis_client()
            )
            self.running = True

            # Reclaimer 시작: cold start 1회 + daemon thread loop
            self._start_reclaimer()

            # Healthz 서버 시작 (127.0.0.1 bind only)
            start_healthz_server(
                stats_provider=lambda: self.stats,
                redis_client=self.redis_client,
                config=self.consumer_config,
            )

            logger.info(
                f"Consumer started successfully. Listening to queue: "
                f"{self.redis_config.QUEUE_STATS_REFRESH}"
            )

            # Main loop
            self._consume_loop()

        except Exception as e:
            logger.error(f"Fatal error in consumer: {e}")
            sentry_sdk.capture_exception(e)
            sys.exit(1)

    def _start_reclaimer(self) -> None:
        """Processing 큐 stuck 메시지 복구 — cold start 후 daemon thread."""
        assert self.redis_client is not None
        reclaimer = ProcessingReclaimer(
            redis_client=self.redis_client,
            config=self.redis_config,
            shutdown_event=get_shutdown_event(),
        )
        # Cold start: 이전 세션의 stuck 메시지 즉시 복구
        try:
            result = reclaimer.reclaim_once()
            if result["reclaimed"] or result["dlq"]:
                logger.warning(f"Cold-start reclaim: {result}")
        except Exception as e:
            logger.error(f"Cold-start reclaim failed: {e}")
            sentry_sdk.capture_exception(e)

        self._reclaimer_thread = threading.Thread(
            target=reclaimer.loop, name="ProcessingReclaimer", daemon=True
        )
        self._reclaimer_thread.start()

    def _lifecycle_service(self):
        """RequestLifecycleService 지연 import (circular 회피)."""
        if self._lifecycle is None:
            from ops_tracking.services import RequestLifecycleService

            self._lifecycle = RequestLifecycleService()
        return self._lifecycle

    @retry(
        stop=stop_after_attempt(30),
        wait=wait_exponential(multiplier=1, min=1, max=60) + wait_random(0, 2),
        retry=retry_if_exception_type(
            (RedisConnectionError, RedisTimeoutError)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _reconnect_with_backoff(self) -> None:
        """Redis 연결을 backoff 재시도. tenacity 로 최대 30회."""
        reset_redis_client()
        self.redis_client = get_redis_client()
        assert self.redis_client is not None
        self.redis_client.client.ping()  # type: ignore[union-attr]
        logger.info("Redis reconnected successfully.")

    def _consume_loop(self) -> None:
        """Main consumption loop.

        Plan.md Phase 5/7: BLMOVE 기반 원자적 pop, heartbeat 매 iteration 갱신,
        max_consecutive_errors 를 ConsumerConfig.MAX_CONSECUTIVE_ERRORS (기본 30) 로.
        """
        consecutive_errors = 0
        max_consecutive_errors = self.consumer_config.MAX_CONSECUTIVE_ERRORS

        while self.running:
            # 매 iteration 에서 heartbeat 갱신 (Phase 7 healthz 의 idle false-stale 방지)
            self.stats["last_heartbeat_at"] = time.time()
            try:
                assert self.redis_client is not None
                # BLMOVE: pending -> processing 원자적 이동 (V1 취약점 제거)
                message = (
                    self.redis_client.blocking_move_pending_to_processing(
                        timeout=self.redis_config.BLOCKING_TIMEOUT
                    )
                )

                if message is None:
                    consecutive_errors = 0
                    continue

                consecutive_errors = 0
                self.stats["last_message_at"] = time.time()

                # Envelope 보강 + lifecycle mark_processing
                message = ensure_envelope(message)
                self._process_message(message)

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                self.shutdown()
                break

            except (RedisConnectionError, RedisTimeoutError) as e:
                consecutive_errors += 1
                logger.warning(
                    f"Redis transient error (consecutive: {consecutive_errors}): {e}"
                )
                try:
                    self._reconnect_with_backoff()
                    consecutive_errors = 0
                except RetryError:
                    logger.critical(
                        "Redis reconnect backoff exhausted. Shutting down."
                    )
                    sentry_sdk.capture_exception(e)
                    self.shutdown()
                    sys.exit(1)

            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Error in consume loop (consecutive: {consecutive_errors}): {e}"
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"Too many consecutive errors ({consecutive_errors}). "
                        f"Shutting down consumer."
                    )
                    sentry_sdk.capture_exception(e)
                    self.shutdown()
                    sys.exit(1)

                # Backoff before retrying (max 32s)
                time.sleep(2 ** min(consecutive_errors, 5))

    def _process_message(self, message: dict) -> None:
        """Process a single message.

        Phase 5 설계: BLMOVE 로 이미 processing 큐에 들어간 상태이므로
        push_to_processing 중복 호출을 제거하고, lifecycle 상태 전이를 수행한다.
        완료 후 processing 큐에서 원본을 LREM 으로 제거.
        """
        import json as _json

        self.processing_message = True
        self.stats["processed"] += 1

        # BLMOVE 가 저장한 processing 엔트리는 pending 에 있던 원본과 동일.
        # ensure_envelope 로 보강된 메시지는 pending 원본과 다를 수 있으므로
        # 구 envelope(보강 전) 기준 raw 도 시도해야 하지만, 여기서는 보강 후
        # 직렬화로 엔트리를 식별한다. BLMOVE 직후 이므로 키 순서는 보존됨.
        original_raw = _json.dumps(message)
        request_id = message.get("requestId")

        # lifecycle: mark_processing (Phase 6 admin 경로에서 mark_queued 가 선행됨.
        # 외부 producer 경로는 mark_queued 가 없을 수 있어 결과는 None 가능.)
        try:
            self._lifecycle_service().mark_processing(
                request_id=request_id,
                retry_count=int(message.get("retryCount", 0)),
                reclaimed_count=int(message.get("reclaimedCount", 0)),
            )
        except Exception as e:
            logger.warning(f"mark_processing failed: {e}")

        try:
            assert self.redis_client is not None
            success = self.message_processor.process_with_retry(message)

            if success:
                self.stats["succeeded"] += 1
                self._safe_lifecycle(
                    "mark_success",
                    request_id=request_id,
                    retry_count=int(message.get("retryCount", 0)),
                )
                logger.info(
                    f"Message processed successfully. Stats: {self._get_stats_summary()}"
                )
            else:
                self.stats["failed"] += 1
                self.redis_client.push_to_failed(message)
                self._safe_lifecycle(
                    "mark_failed",
                    request_id=request_id,
                    error="process_with_retry returned False",
                    retry_count=int(message.get("retryCount", 0)),
                )
                logger.error(
                    f"Message processing failed after all retries. Stats: {self._get_stats_summary()}"
                )

            # processing 큐에서 원본 제거
            self.redis_client.remove_message(
                self.redis_config.QUEUE_STATS_REFRESH_PROCESSING, original_raw
            )

        except Exception as e:
            self.stats["failed"] += 1
            logger.error(f"Unexpected error processing message: {e}")
            sentry_sdk.capture_exception(e)
            try:
                assert self.redis_client is not None
                self.redis_client.push_to_failed(message)
                self.redis_client.remove_message(
                    self.redis_config.QUEUE_STATS_REFRESH_PROCESSING,
                    original_raw,
                )
                self._safe_lifecycle(
                    "mark_failed",
                    request_id=request_id,
                    error=str(e),
                    retry_count=int(message.get("retryCount", 0)),
                )
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup after error: {cleanup_error}")

        finally:
            self.processing_message = False

    def _safe_lifecycle(self, method: str, **kwargs) -> None:
        """ops_tracking 호출이 본 처리 흐름을 방해하지 않도록 try/except."""
        try:
            getattr(self._lifecycle_service(), method)(**kwargs)
        except Exception as e:
            logger.warning(f"lifecycle.{method} failed: {e}")

    def _get_stats_summary(self) -> str:
        """Get consumer statistics summary.

        Returns:
            Statistics summary string
        """
        uptime = time.time() - self.stats["start_time"]
        return (
            f"processed={self.stats['processed']}, "
            f"succeeded={self.stats['succeeded']}, "
            f"failed={self.stats['failed']}, "
            f"uptime={uptime:.0f}s"
        )

    def shutdown(self) -> None:
        """Gracefully shutdown the consumer."""
        if not self.running:
            return

        logger.info("Shutting down consumer...")
        self.running = False

        # Wait for current message processing to complete
        if self.processing_message:
            logger.info("Waiting for current message to finish processing...")
            timeout = self.consumer_config.GRACEFUL_SHUTDOWN_TIMEOUT
            start_time = time.time()

            while (
                self.processing_message
                and (time.time() - start_time) < timeout
            ):
                time.sleep(0.5)

            if self.processing_message:
                logger.warning(
                    "Graceful shutdown timeout reached. "
                    "Current message may not complete."
                )

        # Close Redis connection
        if self.redis_client:
            self.redis_client.close()

        # Log final statistics
        logger.info(
            f"Consumer stopped. Final stats: {self._get_stats_summary()}"
        )


def main() -> None:
    """Main entry point for consumer process."""
    logger.info("=" * 80)
    logger.info("Stats Refresh Consumer")
    logger.info("=" * 80)

    consumer = StatsRefreshConsumer()

    try:
        consumer.start()
    except Exception as e:
        logger.critical(f"Consumer crashed: {e}")
        sentry_sdk.capture_exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
