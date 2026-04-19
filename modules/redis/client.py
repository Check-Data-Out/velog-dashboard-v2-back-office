import json
import logging
from typing import Any, cast

import redis
from redis import Redis, RedisError

from modules.redis.config import RedisConfig

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

    def _push_raw_to_failed(self, raw_message: str, error: str) -> bool:
        """Push raw (unparseable) message to failed queue with error info.

        Returns:
            True on success, False on Redis failure (호출자는 escalate 가능).

        Note:
            큐 크기가 MAX_FAILED_QUEUE_SIZE를 초과하면 오래된 메시지부터 삭제됩니다.
        """
        if not self.client:
            return False

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
            return True
        except RedisError as e:
            logger.error(
                f"Failed to push malformed message to failed queue: {e}"
            )
            return False

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

    # ------------------------------------------------------------------
    # Queue Monitor / Reclaimer 공용 — BLMOVE / 범위 조회 / 원자적 제거
    # ------------------------------------------------------------------

    def blocking_move_pending_to_processing(
        self, timeout: int = 5
    ) -> tuple[str, dict[str, Any]] | None:
        """Pending -> Processing 원자적 이동 (BLMOVE).

        BRPOP + LPUSH 2-step race 를 제거하기 위해 Redis 6.2.0+ 의 BLMOVE 사용.
        https://redis.io/docs/latest/commands/blmove/

        Returns:
            (raw_str, parsed) 튜플. 호출자는 raw_str 을 LREM 원본 비교에 써야 한다.
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            raw_any = self.client.blmove(
                first_list=self.config.QUEUE_STATS_REFRESH,
                second_list=self.config.QUEUE_STATS_REFRESH_PROCESSING,
                timeout=timeout,
                src="RIGHT",
                dest="LEFT",
            )
            if not raw_any:
                return None
            raw = cast(str, raw_any)
            try:
                parsed = json.loads(raw)
                # json.loads 는 Any 반환 — list/str/number 도 가능.
                # https://docs.python.org/3/library/json.html#json.loads
                # dict 가 아니면 malformed 로 간주해 DLQ 로 보낸다.
                if not isinstance(parsed, dict):
                    raise json.JSONDecodeError(
                        f"expected dict, got {type(parsed).__name__}",
                        raw,
                        0,
                    )
                return raw, cast(dict[str, Any], parsed)
            except json.JSONDecodeError as e:
                logger.error(
                    f"BLMOVE received malformed JSON, moving to DLQ: {e}, "
                    f"raw={raw!r}"
                )
                # LREM 성공 후에만 DLQ 이동 — lpush 실패 시에도 호출자에게 신호.
                removed = cast(
                    int,
                    self.client.lrem(
                        self.config.QUEUE_STATS_REFRESH_PROCESSING, 1, raw
                    ),
                )
                if removed == 0:
                    logger.warning(
                        "Malformed entry LREM missed (already gone?)"
                    )
                    return None
                dlq_ok = self._push_raw_to_failed(raw, str(e))
                if not dlq_ok:
                    # processing 에서는 지워졌고 DLQ 에도 못 넣음 → 에러 로그만
                    # (sentry_sdk 는 모듈 레벨 import 없이 상위 레이어가 처리)
                    logger.error(
                        "malformed message lost after LREM (DLQ push failed)"
                    )
                return None
        except RedisError as e:
            logger.error(f"Redis error in BLMOVE: {e}")
            raise

    def get_messages(
        self,
        queue_name: str,
        start: int = 0,
        end: int = -1,
        with_raw: bool = False,
    ) -> list[dict[str, Any]] | list[tuple[str, dict[str, Any]]]:
        """LRANGE + JSON 파싱. 파싱 실패 메시지는 에러 엔트리로 포함.

        with_raw=True 시 (raw_str, parsed) 튜플 리스트 반환. 원본 raw 로 LREM 을
        수행해야 정확 일치가 보장되므로 DLQ retry 경로가 이를 사용한다.
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            raws = self.client.lrange(queue_name, start, end)
        except RedisError as e:
            logger.error(f"Failed to LRANGE {queue_name}: {e}")
            return []

        parsed_only: list[dict[str, Any]] = []
        with_raw_list: list[tuple[str, dict[str, Any]]] = []
        for raw in cast(list[str], raws):
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError:
                parsed: dict[str, Any] = {
                    "_raw": raw,
                    "_error": "JSONDecodeError",
                }
            else:
                # json.loads → Any. list/str/number 도 가능하므로 dict 여부 검증.
                # 호출부(admin/DLQ/reclaimer) 는 .get() 동작을 전제하므로 비-dict 는
                # malformed 로 표시해 동일한 error 엔트리 포맷으로 반환한다.
                if isinstance(loaded, dict):
                    parsed = cast(dict[str, Any], loaded)
                else:
                    parsed = {
                        "_raw": raw,
                        "_error": f"NotADict:{type(loaded).__name__}",
                    }
            if with_raw:
                with_raw_list.append((raw, parsed))
            else:
                parsed_only.append(parsed)
        return with_raw_list if with_raw else parsed_only

    def enqueue_message(self, message: dict[str, Any]) -> None:
        """Pending 큐에 새 메시지 추가 (LPUSH)."""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            self.client.lpush(
                self.config.QUEUE_STATS_REFRESH, json.dumps(message)
            )
            logger.info(
                f"Enqueued to pending: requestId={message.get('requestId')}, "
                f"userId={message.get('userId')}"
            )
        except RedisError as e:
            logger.error(f"Failed to enqueue message: {e}")
            raise

    # Lua CAS: head index 0 == expected_raw 일 때만 LSET.
    # 전체 스크립트가 단일 atomic transaction 으로 실행된다.
    # https://redis.io/docs/latest/commands/eval/
    _REPLACE_HEAD_LUA = """
    local current = redis.call('LINDEX', KEYS[1], 0)
    if current == ARGV[1] then
        redis.call('LSET', KEYS[1], 0, ARGV[2])
        return 1
    end
    return 0
    """

    def replace_processing_head(self, expected_raw: str, new_raw: str) -> bool:
        """Processing 큐 head 가 expected_raw 일 때만 new_raw 로 교체 (CAS).

        BLMOVE 직후 consumer 가 processingStartedAt 을 enrich 한 JSON 을
        Redis 저장값에 반영하기 위해 사용한다. reclaimer thread 가 BLMOVE 와
        LSET 사이에 개입해 head 를 LREM 하는 race 를 Lua LINDEX+LSET CAS 로 차단.

        단일 consumer 전제이지만 reclaimer daemon thread 와 동일 프로세스에서
        동작하므로 BLMOVE→LSET 구간은 threading.Lock 으로 보호되지 않는다.
        Lua 스크립트는 Redis 단일 서버에서 atomic 하게 실행된다.

        Args:
            expected_raw: BLMOVE 가 반환한 원본 raw 문자열
            new_raw: processingStartedAt 이 enrich 된 새 raw 문자열

        Returns:
            CAS 성공(head==expected 일 때 LSET 성공) 여부.
            False 면 호출자는 expected_raw 를 계속 LREM 기준으로 사용해야 한다.
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")
        try:
            result = self.client.eval(
                self._REPLACE_HEAD_LUA,
                1,  # numkeys
                self.config.QUEUE_STATS_REFRESH_PROCESSING,
                expected_raw,
                new_raw,
            )
            return bool(cast(int, result))
        except RedisError as e:
            logger.warning(f"Failed to CAS replace processing head: {e}")
            return False

    def remove_message(self, queue_name: str, message_str: str) -> int:
        """큐에서 문자열이 일치하는 메시지 1건 제거 (LREM count=1). 제거된 수 반환."""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            removed = cast(int, self.client.lrem(queue_name, 1, message_str))
            return removed
        except RedisError as e:
            logger.error(f"Failed to LREM from {queue_name}: {e}")
            return 0

    def flush_queue(self, queue_name: str) -> int:
        """큐 전체 삭제. LLEN + DELETE 를 MULTI/EXEC 로 원자화하여
        감사 count 와 실제 삭제 범위가 동일한 스냅샷이 되도록 한다."""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            with self.client.pipeline(transaction=True) as pipe:
                pipe.llen(queue_name)
                pipe.delete(queue_name)
                size, _ = pipe.execute()
            return cast(int, size)
        except RedisError as e:
            logger.error(f"Failed to flush {queue_name}: {e}")
            return 0

    def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            try:
                self.client.close()
                logger.info("Redis connection closed")
            except RedisError as e:
                logger.error(f"Error closing Redis connection: {e}")
