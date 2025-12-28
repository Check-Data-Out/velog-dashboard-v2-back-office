import json
from unittest.mock import MagicMock, patch

import pytest
from redis import RedisError

from modules.redis.client import (
    RedisQueueClient,
    get_redis_client,
    reset_redis_client,
)


class TestRedisQueueClient:
    """Tests for RedisQueueClient class."""

    @patch("modules.redis.client.redis.Redis")
    def test_init_success(self, mock_redis_class) -> None:
        """Redis 클라이언트 초기화 성공 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()

        assert client.client is not None
        mock_client.ping.assert_called_once()

    @patch("modules.redis.client.redis.Redis")
    def test_init_failure(self, mock_redis_class) -> None:
        """Redis 연결 실패 테스트."""
        mock_redis_class.side_effect = RedisError("Connection failed")

        with pytest.raises(RedisError):
            RedisQueueClient()

    @patch("modules.redis.client.redis.Redis")
    def test_pop_message_success(
        self, mock_redis_class, sample_message
    ) -> None:
        """메시지 pop 성공 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        message_str = json.dumps(sample_message)
        mock_client.brpop.return_value = ("queue_name", message_str)
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.pop_message(timeout=5)

        assert result == sample_message
        mock_client.brpop.assert_called_once()

    @patch("modules.redis.client.redis.Redis")
    def test_pop_message_timeout(self, mock_redis_class) -> None:
        """메시지 pop 타임아웃 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.brpop.return_value = None
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.pop_message(timeout=5)

        assert result is None

    @patch("modules.redis.client.redis.Redis")
    def test_pop_message_invalid_json(self, mock_redis_class) -> None:
        """잘못된 JSON 형식 메시지 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.brpop.return_value = ("queue_name", "invalid json")
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.pop_message(timeout=5)

        assert result is None

    @patch("modules.redis.client.redis.Redis")
    def test_push_to_processing(
        self, mock_redis_class, sample_message
    ) -> None:
        """Processing 큐에 메시지 push 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lpush.return_value = 1
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        client.push_to_processing(sample_message)

        mock_client.lpush.assert_called_once()
        call_args = mock_client.lpush.call_args
        assert json.loads(call_args[0][1]) == sample_message

    @patch("modules.redis.client.redis.Redis")
    def test_push_to_failed(self, mock_redis_class, sample_message) -> None:
        """Failed 큐에 메시지 push 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lpush.return_value = 1
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        client.push_to_failed(sample_message)

        mock_client.lpush.assert_called_once()

    @patch("modules.redis.client.redis.Redis")
    def test_remove_from_processing(
        self, mock_redis_class, sample_message
    ) -> None:
        """Processing 큐에서 메시지 제거 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lrem.return_value = 1
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        client.remove_from_processing(sample_message)

        mock_client.lrem.assert_called_once()

    @patch("modules.redis.client.redis.Redis")
    def test_get_queue_size(self, mock_redis_class) -> None:
        """큐 사이즈 조회 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.llen.return_value = 5
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        size = client.get_queue_size("test_queue")

        assert size == 5
        mock_client.llen.assert_called_once_with("test_queue")

    @patch("modules.redis.client.redis.Redis")
    def test_close(self, mock_redis_class) -> None:
        """Redis 연결 종료 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.close.return_value = None
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        client.close()

        mock_client.close.assert_called_once()


class TestSingletonFunctions:
    """Tests for singleton helper functions."""

    @patch("modules.redis.client.redis.Redis")
    def test_get_redis_client_returns_singleton(
        self, mock_redis_class
    ) -> None:
        """get_redis_client가 동일한 인스턴스를 반환하는지 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        client1 = get_redis_client()
        client2 = get_redis_client()

        assert client1 is client2
        # Redis 연결은 한 번만 생성되어야 함
        assert mock_redis_class.call_count == 1

    @patch("modules.redis.client.redis.Redis")
    def test_reset_redis_client(self, mock_redis_class) -> None:
        """reset_redis_client가 싱글톤을 리셋하는지 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        client1 = get_redis_client()
        reset_redis_client()
        client2 = get_redis_client()

        assert client1 is not client2
        # close가 호출되었는지 확인
        mock_client.close.assert_called()
        # Redis 연결이 두 번 생성되어야 함
        assert mock_redis_class.call_count == 2

    def test_reset_redis_client_when_none(self) -> None:
        """싱글톤이 None일 때 reset_redis_client 호출 테스트."""
        # 에러 없이 실행되어야 함
        reset_redis_client()


class TestDeadLetterQueue:
    """Tests for Dead Letter Queue (DLQ) functionality."""

    @patch("modules.redis.client.redis.Redis")
    def test_pop_message_invalid_json_moves_to_dlq(
        self, mock_redis_class
    ) -> None:
        """JSON 디코딩 실패 시 DLQ로 이동하는지 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.brpop.return_value = ("queue_name", "invalid json {")
        mock_client.lpush.return_value = 1
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.pop_message(timeout=5)

        # None 반환 확인
        assert result is None
        # DLQ에 저장되었는지 확인
        mock_client.lpush.assert_called_once()
        call_args = mock_client.lpush.call_args
        # failed queue에 저장됨
        assert "failed" in call_args[0][0]
        # 저장된 메시지에 raw_message와 error 포함
        saved_message = json.loads(call_args[0][1])
        assert "raw_message" in saved_message
        assert "error" in saved_message
        assert saved_message["error_type"] == "JSONDecodeError"

    @patch("modules.redis.client.redis.Redis")
    def test_push_raw_to_failed(self, mock_redis_class) -> None:
        """_push_raw_to_failed 메서드 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lpush.return_value = 1
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        client._push_raw_to_failed("raw message", "test error")

        mock_client.lpush.assert_called_once()
        call_args = mock_client.lpush.call_args
        saved_message = json.loads(call_args[0][1])
        assert saved_message["raw_message"] == "raw message"
        assert saved_message["error"] == "test error"

    @patch("modules.redis.client.redis.Redis")
    def test_push_to_failed_with_ltrim(
        self, mock_redis_class, sample_message
    ) -> None:
        """push_to_failed가 LTRIM으로 큐 크기를 제한하는지 테스트."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lpush.return_value = 1
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        client.push_to_failed(sample_message)

        # lpush와 ltrim 모두 호출되었는지 확인
        mock_client.lpush.assert_called_once()
        mock_client.ltrim.assert_called_once()
        # ltrim이 올바른 범위로 호출되었는지 확인
        ltrim_args = mock_client.ltrim.call_args[0]
        assert ltrim_args[1] == 0  # start
        assert ltrim_args[2] == client.config.MAX_FAILED_QUEUE_SIZE - 1  # end
