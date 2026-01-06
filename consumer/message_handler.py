import asyncio
import logging
import time
from typing import Any

import sentry_sdk

from consumer.config import RedisConfig
from scraping.main import ScraperTargetUser
from utils.utils import get_local_now

logger = logging.getLogger("consumer")


class StatsRefreshMessageHandler:
    """Handler for stats refresh messages."""

    def __init__(self, config: type[RedisConfig] | None = None) -> None:
        """Initialize message handler.

        Args:
            config: RedisConfig 클래스 (DI 지원, 기본값: RedisConfig)
        """
        self.config = config or RedisConfig

    async def process_message(self, message: dict[str, Any]) -> None:
        """Process a stats refresh message.

        Args:
            message: Message containing user_id and other metadata

        Raises:
            ValueError: If message format is invalid
            Exception: If processing fails
        """
        # Validate message format
        if "userId" not in message:
            raise ValueError("Message missing required field: userId")

        user_id = message["userId"]
        requested_at = message.get("requestedAt", "")
        retry_count = message.get("retryCount", 0)

        logger.info(
            f"Processing stats refresh for user_id={user_id}, "
            f"requested_at={requested_at}, retry={retry_count}"
        )

        start_time = time.time()

        try:
            # Execute scraping using ScraperTargetUser
            scraper = ScraperTargetUser(
                user_pk_list=[user_id], max_connections=40
            )
            await scraper.run()

            elapsed_time = time.time() - start_time
            logger.info(
                f"Successfully processed stats refresh for user_id={user_id} "
                f"in {elapsed_time:.2f}s"
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                f"Failed to process stats refresh for user_id={user_id} "
                f"after {elapsed_time:.2f}s: {e}"
            )
            sentry_sdk.capture_exception(e)
            raise

    def handle_message_sync(self, message: dict[str, Any]) -> None:
        """Synchronous wrapper for processing message.

        Args:
            message: Message to process
        """
        asyncio.run(self.process_message(message))


class MessageProcessor:
    """Processor with retry logic for messages."""

    def __init__(self, config: type[RedisConfig] | None = None) -> None:
        """Initialize message processor.

        Args:
            config: RedisConfig 클래스 (DI 지원, 기본값: RedisConfig)
        """
        self.config = config or RedisConfig
        self.handler = StatsRefreshMessageHandler(config=self.config)

    def process_with_retry(self, message: dict[str, Any]) -> bool:
        """Process message with retry logic.

        Args:
            message: Message to process

        Returns:
            True if processing succeeded, False otherwise
        """
        max_retries = self.config.MAX_RETRIES
        retry_count = message.get("retryCount", 0)

        for attempt in range(max_retries):
            try:
                # Update retry count in message
                message["retryCount"] = retry_count + attempt
                message["lastAttemptAt"] = get_local_now().isoformat()

                # Process the message
                self.handler.handle_message_sync(message)

                # Success
                return True

            except ValueError as e:
                # Invalid message format - don't retry
                logger.error(f"Invalid message format: {e}")
                sentry_sdk.capture_exception(e)
                return False

            except Exception as e:
                # Processing failed
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for "
                    f"user_id={message.get('userId')}: {e}"
                )

                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt seconds
                    backoff_time = self.config.RETRY_BACKOFF_BASE**attempt
                    logger.info(f"Retrying in {backoff_time}s...")
                    time.sleep(backoff_time)
                else:
                    # Final failure
                    logger.error(
                        f"All {max_retries} attempts failed for "
                        f"user_id={message.get('userId')}"
                    )
                    sentry_sdk.capture_exception(e)
                    return False

        return False
