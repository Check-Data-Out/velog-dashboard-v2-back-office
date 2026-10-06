import json
from unittest.mock import MagicMock, patch

from redis import RedisError
from redis.exceptions import WatchError

from modules.redis.client import RedisQueueClient
from modules.redis.config import RedisConfig


class TestBlockingMovePendingToProcessing:
    @patch("modules.redis.client.redis.Redis")
    def test_returns_raw_and_parsed_when_available(
        self, mock_redis_class, sample_message
    ):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        raw = json.dumps(sample_message)
        mock_client.blmove.return_value = raw
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.blocking_move_pending_to_processing(timeout=5)

        # (raw_str, parsed) 튜플 반환 — 호출자는 raw_str 로 LREM 원본 비교
        assert result == (raw, sample_message)
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

    @patch("modules.redis.client.redis.Redis")
    def test_non_dict_json_is_rejected_as_malformed(self, mock_redis_class):
        """json.loads 가 list/str/int 를 반환하면 malformed 로 DLQ 이동."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        # valid JSON 이지만 dict 가 아님 (list)
        mock_client.blmove.return_value = "[1, 2, 3]"
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        assert client.blocking_move_pending_to_processing(timeout=5) is None
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

    @patch("modules.redis.client.redis.Redis")
    def test_non_dict_json_entry_surfaces_as_error(self, mock_redis_class):
        """valid JSON 이지만 dict 가 아닌 엔트리(list/str/number)는 error 로 표시."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        # list JSON, number JSON, string JSON, valid dict JSON
        mock_client.lrange.return_value = [
            "[1, 2]",
            "42",
            '"just a string"',
            '{"userId": 1}',
        ]
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        result = client.get_messages("any-queue")
        assert result[0]["_error"] == "NotADict:list"
        assert result[1]["_error"] == "NotADict:int"
        assert result[2]["_error"] == "NotADict:str"
        assert result[3]["userId"] == 1
        # with_raw=True 에서도 dict 로 일관 반환 (.get() 호출 안전)
        raw_result = client.get_messages("any-queue", with_raw=True)
        for _, parsed in raw_result:
            assert isinstance(parsed, dict)
            assert parsed.get("_error") or parsed.get("userId")  # 둘 중 하나


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


class TestReplaceProcessingHead:
    """WATCH/MULTI CAS 로 head 교체 — reclaimer 와의 race 를 재시도로 흡수한다."""

    KEY = RedisConfig.QUEUE_STATS_REFRESH_PROCESSING

    def _client_with_pipe(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        pipe = MagicMock()
        mock_client.pipeline.return_value.__enter__.return_value = pipe
        mock_redis_class.return_value = mock_client
        return RedisQueueClient(), pipe

    @patch("modules.redis.client.redis.Redis")
    def test_cas_match_returns_true(self, mock_redis_class):
        client, pipe = self._client_with_pipe(mock_redis_class)
        pipe.lindex.return_value = "expected-raw"
        pipe.execute.return_value = [True]

        ok = client.replace_processing_head("expected-raw", "new-raw")

        assert ok is True
        pipe.watch.assert_called_once_with(self.KEY)
        pipe.lindex.assert_called_once_with(self.KEY, 0)
        pipe.lset.assert_called_once_with(self.KEY, 0, "new-raw")
        pipe.execute.assert_called_once()

    @patch("modules.redis.client.redis.Redis")
    def test_cas_mismatch_returns_false_without_lset(self, mock_redis_class):
        """reclaimer 가 head 를 LREM/수정했다면 UNWATCH 후 False."""
        client, pipe = self._client_with_pipe(mock_redis_class)
        pipe.lindex.return_value = "other-raw"

        ok = client.replace_processing_head("expected-raw", "new-raw")

        assert ok is False
        pipe.unwatch.assert_called_once()
        pipe.lset.assert_not_called()
        pipe.execute.assert_not_called()

    @patch("modules.redis.client.redis.Redis")
    def test_watch_error_retries_and_succeeds(self, mock_redis_class):
        """EXEC 이 WatchError 로 취소되면 head 를 다시 확인하고 재시도한다."""
        client, pipe = self._client_with_pipe(mock_redis_class)
        pipe.lindex.side_effect = ["expected-raw", "expected-raw"]
        pipe.execute.side_effect = [WatchError("changed"), [True]]

        ok = client.replace_processing_head("expected-raw", "new-raw")

        assert ok is True
        assert pipe.lset.call_count == 2
        assert pipe.execute.call_count == 2

    @patch("modules.redis.client.redis.Redis")
    def test_watch_error_then_mismatch_returns_false(self, mock_redis_class):
        """재시도 중 head 가 바뀌어 있으면 더 이상 LSET 하지 않고 False."""
        client, pipe = self._client_with_pipe(mock_redis_class)
        pipe.lindex.side_effect = ["expected-raw", "other-raw"]
        pipe.execute.side_effect = [WatchError("changed")]

        ok = client.replace_processing_head("expected-raw", "new-raw")

        assert ok is False
        assert pipe.lset.call_count == 1
        pipe.unwatch.assert_called_once()

    @patch("modules.redis.client.redis.Redis")
    def test_redis_error_returns_false(self, mock_redis_class):
        """RedisError 는 밖으로 내지 않고 False (호출자가 LREM 기준 유지)."""
        client, pipe = self._client_with_pipe(mock_redis_class)
        pipe.watch.side_effect = RedisError("boom")

        assert (
            client.replace_processing_head("expected-raw", "new-raw") is False
        )


class TestFlushQueue:
    @patch("modules.redis.client.redis.Redis")
    def test_returns_size_then_deletes(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        # pipeline().__enter__ → pipe, pipe.execute() → [llen, delete] 결과
        pipe = MagicMock()
        pipe.execute.return_value = [42, True]
        mock_client.pipeline.return_value.__enter__.return_value = pipe
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        removed = client.flush_queue("any-queue")
        assert removed == 42
        pipe.llen.assert_called_once_with("any-queue")
        pipe.delete.assert_called_once_with("any-queue")
