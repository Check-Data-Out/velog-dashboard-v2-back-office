"""Phase 2 — RedisQueueClient 확장 메서드 테스트.

BLMOVE / get_messages / enqueue_message / remove_message / flush_queue.
"""

import json
from unittest.mock import MagicMock, patch

from modules.redis.client import RedisQueueClient


class TestBlockingMovePendingToProcessing:
    @patch("modules.redis.client.redis.Redis")
    def test_returns_parsed_message_when_available(
        self, mock_redis_class, sample_message
    ):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.blmove.return_value = json.dumps(sample_message)
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.blocking_move_pending_to_processing(timeout=5)

        assert result == sample_message
        mock_client.blmove.assert_called_once()
        kwargs = mock_client.blmove.call_args.kwargs
        assert kwargs["src"] == "RIGHT"
        assert kwargs["dest"] == "LEFT"

    @patch("modules.redis.client.redis.Redis")
    def test_returns_none_on_timeout(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.blmove.return_value = None
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        assert client.blocking_move_pending_to_processing(timeout=5) is None

    @patch("modules.redis.client.redis.Redis")
    def test_malformed_json_moves_to_dlq_and_returns_none(
        self, mock_redis_class
    ):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.blmove.return_value = "not-json"
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        assert client.blocking_move_pending_to_processing(timeout=5) is None
        # processing 에서 제거 + DLQ 저장
        mock_client.lrem.assert_called_once()
        mock_client.lpush.assert_called_once()


class TestGetMessages:
    @patch("modules.redis.client.redis.Redis")
    def test_returns_parsed_list(self, mock_redis_class, sample_message):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lrange.return_value = [
            json.dumps(sample_message),
            json.dumps({"userId": 999}),
        ]
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.get_messages("any-queue", 0, -1)
        assert len(result) == 2
        assert result[0] == sample_message
        assert result[1]["userId"] == 999

    @patch("modules.redis.client.redis.Redis")
    def test_empty_queue_returns_empty_list(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lrange.return_value = []
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        assert client.get_messages("any-queue") == []

    @patch("modules.redis.client.redis.Redis")
    def test_malformed_entry_surfaces_as_raw_error(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lrange.return_value = ["not-json", '{"userId": 1}']
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.get_messages("any-queue")
        assert result[0]["_error"] == "JSONDecodeError"
        assert result[0]["_raw"] == "not-json"
        assert result[1]["userId"] == 1


class TestEnqueueMessage:
    @patch("modules.redis.client.redis.Redis")
    def test_lpush_to_pending_queue(self, mock_redis_class, sample_message):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        client.enqueue_message(sample_message)
        mock_client.lpush.assert_called_once()
        args = mock_client.lpush.call_args[0]
        assert args[0] == client.config.QUEUE_STATS_REFRESH
        assert json.loads(args[1]) == sample_message


class TestRemoveMessage:
    @patch("modules.redis.client.redis.Redis")
    def test_returns_removed_count(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.lrem.return_value = 1
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        removed = client.remove_message("any-queue", "some-str")
        assert removed == 1
        mock_client.lrem.assert_called_once_with("any-queue", 1, "some-str")


class TestFlushQueue:
    @patch("modules.redis.client.redis.Redis")
    def test_returns_size_then_deletes(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.llen.return_value = 42
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        removed = client.flush_queue("any-queue")
        assert removed == 42
        mock_client.delete.assert_called_once_with("any-queue")
