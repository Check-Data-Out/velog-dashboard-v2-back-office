import json
import logging
from typing import Any, cast

import redis
from redis import Redis, RedisError

from consumer.config import RedisConfig

logger = logging.getLogger(__name__)

# 모듈 레벨 싱글톤 인스턴스
_client: "RedisQueueClient | None" = None


def get_redis_client() -> "RedisQueueClient":
    """글로벌 싱글톤 Redis 클라이언트 반환.

    Returns:
        RedisQueueClient 싱글톤 인스턴스
    """
    global _client
    if _client is None:
        _client = RedisQueueClient()
    return _client


def reset_redis_client() -> None:
    """싱글톤 인스턴스 리셋 (테스트용).

    기존 연결을 닫고 싱글톤 인스턴스를 None으로 초기화합니다.
    """
    global _client
    if _client is not None:
        _client.close()
        _client = None


class RedisQueueClient:
    """Redis client for queue operations."""

    def __init__(self, config: type[RedisConfig] | None = None) -> None:
        """Initialize Redis client.

        Args:
            config: RedisConfig 클래스 (DI 지원, 기본값: RedisConfig)
        """
        self.config = config or RedisConfig
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
                _, message_str = cast(tuple[str, str], result)
                try:
                    message: dict[str, Any] = json.loads(message_str)
                    logger.debug(f"Popped message from queue: {message}")
                    return message
                except json.JSONDecodeError as e:
                    # JSON 디코딩 실패 시 원본 문자열을 DLQ(failed queue)에 저장
                    # https://ctaverna.github.io/dead-letters/
                    logger.error(
                        f"Failed to decode message, moving to failed queue: {e}, "
                        f"raw_message={message_str!r}"
                    )
                    self._push_raw_to_failed(message_str, str(e))
                    return None
            return None
        except RedisError as e:
            logger.error(f"Redis error while popping message: {e}")
            raise

    def _push_raw_to_failed(self, raw_message: str, error: str) -> None:
        """Push raw (unparseable) message to failed queue with error info.

        Args:
            raw_message: Original message string that failed to decode
            error: Error message describing the failure

        Note:
            큐 크기가 MAX_FAILED_QUEUE_SIZE를 초과하면 오래된 메시지부터 삭제됩니다.
        """
        if not self.client:
            return

        try:
            # 원본 메시지와 에러 정보를 함께 저장
            failed_entry = json.dumps(
                {
                    "raw_message": raw_message,
                    "error": error,
                    "error_type": "JSONDecodeError",
                }
            )
            self.client.lpush(
                self.config.QUEUE_STATS_REFRESH_FAILED, failed_entry
            )
            # 큐 크기 제한
            self.client.ltrim(
                self.config.QUEUE_STATS_REFRESH_FAILED,
                0,
                self.config.MAX_FAILED_QUEUE_SIZE - 1,
            )
            logger.warning("Pushed malformed message to failed queue")
        except RedisError as e:
            logger.error(
                f"Failed to push malformed message to failed queue: {e}"
            )

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
        """Push message to failed queue with size limit.

        Args:
            message: Message to push

        Note:
            큐 크기가 MAX_FAILED_QUEUE_SIZE를 초과하면 오래된 메시지부터 삭제됩니다.
            https://redis.io/glossary/redis-queue/
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            message_str = json.dumps(message)
            self.client.lpush(
                self.config.QUEUE_STATS_REFRESH_FAILED, message_str
            )
            # 큐 크기 제한 - LTRIM으로 최대 크기 유지
            self.client.ltrim(
                self.config.QUEUE_STATS_REFRESH_FAILED,
                0,
                self.config.MAX_FAILED_QUEUE_SIZE - 1,
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
            result = cast(int, self.client.llen(queue_name))
            return result
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
