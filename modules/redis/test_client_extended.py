import json
from unittest.mock import MagicMock, patch

from modules.redis.client import RedisQueueClient


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
    """Lua CAS 로 head 교체 — reclaimer 와의 race 를 atomic 하게 차단한다."""

    @patch("modules.redis.client.redis.Redis")
    def test_cas_match_returns_true(self, mock_redis_class):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.eval.return_value = 1  # Lua 1 반환 = match + LSET 성공
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        ok = client.replace_processing_head("expected-raw", "new-raw")
        assert ok is True
        mock_client.eval.assert_called_once()
        args = mock_client.eval.call_args[0]
        # (script, numkeys, key, expected, new)
        assert args[1] == 1
        assert args[2] == client.config.QUEUE_STATS_REFRESH_PROCESSING
        assert args[3] == "expected-raw"
        assert args[4] == "new-raw"

    @patch("modules.redis.client.redis.Redis")
    def test_cas_mismatch_returns_false(self, mock_redis_class):
        """reclaimer 가 head 를 LREM/수정했다면 CAS 가 0 반환 → False."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.eval.return_value = 0
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
        assert (
            client.replace_processing_head("expected-raw", "new-raw") is False
        )

    @patch("modules.redis.client.redis.Redis")
    def test_redis_error_returns_false(self, mock_redis_class):
        from redis import RedisError

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.eval.side_effect = RedisError("boom")
        mock_redis_class.return_value = mock_client

        client = RedisQueueClient()
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
