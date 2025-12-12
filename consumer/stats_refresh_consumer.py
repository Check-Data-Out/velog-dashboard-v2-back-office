import signal
import sys
import time

import sentry_sdk

# Django setup must be imported first
import consumer.setup_django  # noqa: F401
from consumer.config import ConsumerConfig, RedisConfig
from consumer.logger_config import setup_logger
from consumer.message_handler import MessageProcessor
from modules.redis.client import RedisQueueClient

logger = setup_logger()


class StatsRefreshConsumer:
    """Main consumer process for stats refresh queue."""

    def __init__(self) -> None:
        """Initialize consumer."""
        self.redis_client: RedisQueueClient | None = None
        self.message_processor = MessageProcessor()
        self.running = False
        self.processing_message = False
        self.redis_config = RedisConfig()
        self.consumer_config = ConsumerConfig()

        # Statistics
        self.stats = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "start_time": time.time(),
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
            # Initialize Redis client
            self.redis_client = RedisQueueClient()
            self.running = True

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

    def _consume_loop(self) -> None:
        """Main consumption loop."""
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.running:
            try:
                # Pop message from queue (blocking)
                assert self.redis_client is not None
                message = self.redis_client.pop_message(
                    timeout=self.redis_config.BLOCKING_TIMEOUT
                )

                if message is None:
                    # Timeout - no message available
                    consecutive_errors = 0
                    continue

                # Reset error counter on successful pop
                consecutive_errors = 0

                # Process the message
                self._process_message(message)

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                self.shutdown()
                break

            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Error in consume loop (consecutive: {consecutive_errors}): {e}"
                )
                sentry_sdk.capture_exception(e)

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"Too many consecutive errors ({consecutive_errors}). "
                        f"Shutting down consumer."
                    )
                    self.shutdown()
                    sys.exit(1)

                # Backoff before retrying
                time.sleep(2 ** min(consecutive_errors, 5))

    def _process_message(self, message: dict) -> None:
        """Process a single message.

        Args:
            message: Message to process
        """
        self.processing_message = True
        self.stats["processed"] += 1

        try:
            # Move to processing queue
            assert self.redis_client is not None
            self.redis_client.push_to_processing(message)

            # Process with retry logic
            success = self.message_processor.process_with_retry(message)

            if success:
                self.stats["succeeded"] += 1
                logger.info(
                    f"Message processed successfully. "
                    f"Stats: {self._get_stats_summary()}"
                )
            else:
                self.stats["failed"] += 1
                # Move to failed queue
                self.redis_client.push_to_failed(message)
                logger.error(
                    f"Message processing failed after all retries. "
                    f"Stats: {self._get_stats_summary()}"
                )

            # Remove from processing queue
            self.redis_client.remove_from_processing(message)

        except Exception as e:
            self.stats["failed"] += 1
            logger.error(f"Unexpected error processing message: {e}")
            sentry_sdk.capture_exception(e)

            # Try to move to failed queue
            try:
                assert self.redis_client is not None
                self.redis_client.push_to_failed(message)
                self.redis_client.remove_from_processing(message)
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup after error: {cleanup_error}")

        finally:
            self.processing_message = False

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
