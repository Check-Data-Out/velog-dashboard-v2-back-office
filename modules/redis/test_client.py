import json
from unittest.mock import MagicMock, patch

import pytest
from redis import RedisError

from modules.redis.client import RedisQueueClient


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
