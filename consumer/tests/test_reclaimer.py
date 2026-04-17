"""Phase 5 — ProcessingReclaimer 테스트.

fakeredis 사용 없이 MagicMock 으로 get_messages/remove_message/enqueue/push_to_failed
동작만 검증 (플랜 §4.3: Redis 자체 연산은 redis-py/fakeredis 가 보장).
"""

import json
import time
from unittest.mock import MagicMock

from modules.redis.config import RedisConfig


def _make_client():
    client = MagicMock()
    client.config = RedisConfig
    client.get_messages = MagicMock(return_value=[])
    client.remove_message = MagicMock(return_value=1)
    client.enqueue_message = MagicMock()
    client.push_to_failed = MagicMock()
    return client


def _make_reclaimer(client, visibility=600, max_reclaims=3):
    from consumer.reclaimer import ProcessingReclaimer

    class _TestConfig(RedisConfig):
        RECLAIM_VISIBILITY_TIMEOUT_SEC = visibility
        RECLAIM_MAX_RECLAIMS = max_reclaims
        RECLAIM_INTERVAL_SEC = 0  # loop 테스트 시 즉시 종료 유도

    return ProcessingReclaimer(client, config=_TestConfig)


class TestReclaimOnce:
    def test_stale_message_moves_from_processing_to_pending(self):
        client = _make_client()
        now = time.time()
        stale = {
            "requestId": "rid-stale",
            "userId": 1,
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 1000)
            ),
            "reclaimedCount": 0,
            "retryCount": 2,
        }
        raw = json.dumps(stale)
        client.get_messages.return_value = [(raw, stale)]
        reclaimer = _make_reclaimer(client, visibility=600)
        counts = reclaimer.reclaim_once(now_epoch=now)
        assert counts == {"reclaimed": 1, "dlq": 0, "fresh": 0}
        client.remove_message.assert_called_once_with(
            RedisConfig.QUEUE_STATS_REFRESH_PROCESSING, raw
        )
        pushed = client.enqueue_message.call_args[0][0]
        assert pushed["reclaimedCount"] == 1
        assert pushed["retryCount"] == 0

    def test_fresh_message_is_not_reclaimed(self):
        client = _make_client()
        now = time.time()
        fresh = {
            "requestId": "rid-fresh",
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 10)
            ),
        }
        client.get_messages.return_value = [(json.dumps(fresh), fresh)]
        reclaimer = _make_reclaimer(client, visibility=600)
        counts = reclaimer.reclaim_once(now_epoch=now)
        assert counts == {"reclaimed": 0, "dlq": 0, "fresh": 1}
        client.remove_message.assert_not_called()
        client.enqueue_message.assert_not_called()

    def test_max_reclaims_exceeded_moves_to_dlq(self):
        client = _make_client()
        now = time.time()
        stale = {
            "requestId": "rid-poison",
            "userId": 9,
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 9999)
            ),
            "reclaimedCount": 3,  # MAX=3 → +1 = 4 > 3 → DLQ
        }
        client.get_messages.return_value = [(json.dumps(stale), stale)]
        reclaimer = _make_reclaimer(client, visibility=600, max_reclaims=3)
        counts = reclaimer.reclaim_once(now_epoch=now)
        assert counts == {"reclaimed": 0, "dlq": 1, "fresh": 0}
        client.push_to_failed.assert_called_once()
        client.enqueue_message.assert_not_called()

    def test_remove_message_race_skips_entry(self):
        client = _make_client()
        client.remove_message.return_value = 0  # 다른 consumer 가 이미 처리
        now = time.time()
        stale = {
            "requestId": "rid-race",
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 1000)
            ),
            "reclaimedCount": 0,
        }
        client.get_messages.return_value = [(json.dumps(stale), stale)]
        reclaimer = _make_reclaimer(client, visibility=600)
        counts = reclaimer.reclaim_once(now_epoch=now)
        # race 후 skip
        assert counts["reclaimed"] == 0
        client.enqueue_message.assert_not_called()

    def test_malformed_parsed_entry_moves_to_dlq(self):
        client = _make_client()
        bad_parsed = {"_raw": "garbage", "_error": "JSONDecodeError"}
        client.get_messages.return_value = [("garbage", bad_parsed)]
        reclaimer = _make_reclaimer(client)
        counts = reclaimer.reclaim_once(now_epoch=time.time())
        assert counts["dlq"] == 1
        client.push_to_failed.assert_called_once_with(bad_parsed)


class TestLoop:
    def test_loop_stops_when_shutdown_event_set(self):
        import threading

        from consumer.reclaimer import ProcessingReclaimer

        client = _make_client()
        event = threading.Event()

        class _C(RedisConfig):
            RECLAIM_INTERVAL_SEC = 0

        reclaimer = ProcessingReclaimer(
            client, config=_C, shutdown_event=event
        )
        event.set()  # 시작 전에 set → 루프 즉시 종료
        reclaimer.loop()
        # exception 없이 종료되면 성공
