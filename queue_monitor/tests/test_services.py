from unittest.mock import MagicMock

import pytest

from modules.redis.config import RedisConfig
from queue_monitor.services import QueueMonitorService


@pytest.fixture
def mock_redis_client():
    c = MagicMock()
    c.config = RedisConfig
    c.enqueue_message = MagicMock()
    c.get_queue_size = MagicMock(return_value=0)
    c.get_messages = MagicMock(return_value=[])
    c.remove_message = MagicMock(return_value=1)
    c.flush_queue = MagicMock(return_value=0)
    return c


class TestEnqueueStatsRefresh:
    def test_pushes_one_message_per_user(self, mock_redis_client):
        service = QueueMonitorService(redis_client=mock_redis_client)
        queued, skipped = service.enqueue_stats_refresh(
            user_ids=[1, 2, 3], requested_by=99
        )
        assert queued == 3
        assert skipped == 0
        assert mock_redis_client.enqueue_message.call_count == 3
        envelope = mock_redis_client.enqueue_message.call_args_list[0][0][0]
        assert envelope["userId"] == 1
        assert envelope["requestedBy"] == 99
        assert envelope["requestId"]

    def test_skips_listed_user_ids(self, mock_redis_client):
        service = QueueMonitorService(redis_client=mock_redis_client)
        queued, skipped = service.enqueue_stats_refresh(
            user_ids=[1, 2, 3], requested_by=None, skip_user_ids={2}
        )
        assert queued == 2
        assert skipped == 1


class TestRetryFailedMessage:
    def test_moves_from_failed_to_pending_and_resets_retry_count(
        self, mock_redis_client
    ):
        # 서비스는 get_messages(with_raw=True) 로 (raw, parsed) 튜플을 받음
        failed_raw = '{"requestId": "rid-1", "userId": 5, "retryCount": 3, "reclaimedCount": 1}'
        failed_msg = {
            "requestId": "rid-1",
            "userId": 5,
            "retryCount": 3,
            "reclaimedCount": 1,
        }
        mock_redis_client.get_messages.return_value = [
            (failed_raw, failed_msg)
        ]
        service = QueueMonitorService(redis_client=mock_redis_client)
        ok = service.retry_failed_message("rid-1")
        assert ok is True
        # remove_message 는 **원본 raw 문자열** 그대로 호출되어야 한다
        mock_redis_client.remove_message.assert_called_once_with(
            RedisConfig.QUEUE_STATS_REFRESH_FAILED, failed_raw
        )
        # enqueue 는 retryCount 리셋된 메시지
        pushed = mock_redis_client.enqueue_message.call_args[0][0]
        assert pushed["requestId"] == "rid-1"
        assert pushed["retryCount"] == 0
        assert pushed["reclaimedCount"] == 1

    def test_returns_false_when_request_id_not_found(self, mock_redis_client):
        mock_redis_client.get_messages.return_value = [
            (
                '{"requestId": "other", "userId": 1}',
                {"requestId": "other", "userId": 1},
            )
        ]
        service = QueueMonitorService(redis_client=mock_redis_client)
        assert service.retry_failed_message("rid-missing") is False
        mock_redis_client.remove_message.assert_not_called()
        mock_redis_client.enqueue_message.assert_not_called()

    def test_returns_false_when_remove_fails(self, mock_redis_client):
        raw = '{"requestId": "rid-1", "userId": 5}'
        mock_redis_client.get_messages.return_value = [
            (raw, {"requestId": "rid-1", "userId": 5})
        ]
        mock_redis_client.remove_message.return_value = 0
        service = QueueMonitorService(redis_client=mock_redis_client)
        assert service.retry_failed_message("rid-1") is False
        mock_redis_client.enqueue_message.assert_not_called()

    def test_restores_to_dlq_when_enqueue_fails(self, mock_redis_client):
        """리뷰: LREM 성공 후 pending enqueue 실패 시 DLQ 복구로 유실 방지."""
        raw = '{"requestId": "rid-2", "userId": 5}'
        mock_redis_client.get_messages.return_value = [
            (raw, {"requestId": "rid-2", "userId": 5})
        ]
        mock_redis_client.remove_message.return_value = 1
        mock_redis_client.enqueue_message.side_effect = Exception("redis down")
        mock_redis_client.push_to_failed = MagicMock()
        service = QueueMonitorService(redis_client=mock_redis_client)
        assert service.retry_failed_message("rid-2") is False
        # 실패 시 DLQ 로 best-effort 복구 시도
        mock_redis_client.push_to_failed.assert_called_once()


class TestPurgeFailed:
    def test_returns_flushed_count(self, mock_redis_client):
        mock_redis_client.flush_queue.return_value = 7
        service = QueueMonitorService(redis_client=mock_redis_client)
        assert service.purge_failed() == 7
        mock_redis_client.flush_queue.assert_called_once_with(
            RedisConfig.QUEUE_STATS_REFRESH_FAILED
        )


class TestGetQueueStats:
    def test_returns_three_counters(self, mock_redis_client):
        mock_redis_client.get_queue_size.side_effect = [10, 2, 3]
        service = QueueMonitorService(redis_client=mock_redis_client)
        stats = service.get_queue_stats()
        assert stats == {"pending": 10, "processing": 2, "failed": 3}
