import json
import logging
from typing import Any

import redis
from redis import Redis, RedisError

from consumer.config import RedisConfig

logger = logging.getLogger("consumer")


class RedisQueueClient:
    """Redis client for queue operations."""

    def __init__(self) -> None:
        """Initialize Redis client."""
        self.config = RedisConfig()
        self.client: Redis | None = None
        self._connect()

    def _connect(self) -> None:
        """Establish Redis connection."""
        try:
            self.client = redis.Redis(
                host=self.config.HOST,
                port=self.config.PORT,
                password=self.config.PASSWORD,
                db=self.config.DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            # Test connection
            self.client.ping()
            logger.info(
                f"Redis connection established: {self.config.HOST}:{self.config.PORT}"
            )
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def pop_message(self, timeout: int = 5) -> dict[str, Any] | None:
        """Pop a message from the stats refresh queue (blocking).

        Args:
            timeout: Blocking timeout in seconds

        Returns:
            Message dict if available, None if timeout
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            result = self.client.brpop(
                [self.config.QUEUE_STATS_REFRESH], timeout=timeout
            )
            if result:
                _, message_str = result  # type: ignore
                message = json.loads(message_str)
                logger.debug(f"Popped message from queue: {message}")
                return message
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message: {e}")
            return None
        except RedisError as e:
            logger.error(f"Redis error while popping message: {e}")
            raise

    def push_to_processing(self, message: dict[str, Any]) -> None:
        """Push message to processing queue.

        Args:
            message: Message to push
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            message_str = json.dumps(message)
            self.client.lpush(
                self.config.QUEUE_STATS_REFRESH_PROCESSING, message_str
            )
            logger.debug(f"Pushed message to processing queue: {message}")
        except RedisError as e:
            logger.error(f"Failed to push to processing queue: {e}")
            raise

    def remove_from_processing(self, message: dict[str, Any]) -> None:
        """Remove message from processing queue.

        Args:
            message: Message to remove
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            message_str = json.dumps(message)
            self.client.lrem(
                self.config.QUEUE_STATS_REFRESH_PROCESSING, 1, message_str
            )
            logger.debug(f"Removed message from processing queue: {message}")
        except RedisError as e:
            logger.error(f"Failed to remove from processing queue: {e}")
            raise

    def push_to_failed(self, message: dict[str, Any]) -> None:
        """Push message to failed queue.

        Args:
            message: Message to push
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            message_str = json.dumps(message)
            self.client.lpush(
                self.config.QUEUE_STATS_REFRESH_FAILED, message_str
            )
            logger.warning(f"Pushed message to failed queue: {message}")
        except RedisError as e:
            logger.error(f"Failed to push to failed queue: {e}")
            raise

    def get_queue_size(self, queue_name: str) -> int:
        """Get the size of a queue.

        Args:
            queue_name: Name of the queue

        Returns:
            Queue size
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return self.client.llen(queue_name)  # type: ignore
        except RedisError as e:
            logger.error(f"Failed to get queue size: {e}")
            return 0

    def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            try:
                self.client.close()
                logger.info("Redis connection closed")
            except RedisError as e:
                logger.error(f"Error closing Redis connection: {e}")
