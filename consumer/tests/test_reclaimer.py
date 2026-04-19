import json
import threading
import time
from unittest.mock import MagicMock

from consumer.reclaimer import ProcessingReclaimer
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

    def test_malformed_entry_lrem_miss_does_not_push_to_dlq(self):
        """리뷰: malformed entry LREM 실패 시 DLQ 중복 적재 방지."""
        client = _make_client()
        client.remove_message.return_value = 0  # race: 이미 다른 주기가 처리
        bad_parsed = {"_raw": "garbage", "_error": "JSONDecodeError"}
        client.get_messages.return_value = [("garbage", bad_parsed)]
        reclaimer = _make_reclaimer(client)
        counts = reclaimer.reclaim_once(now_epoch=time.time())
        assert counts["dlq"] == 0
        client.push_to_failed.assert_not_called()

    def test_uses_processing_started_at_over_enqueued_at(self):
        """리뷰: pending 장기대기 메시지가 BLMOVE 직후 즉시 stale 되지 않음."""
        client = _make_client()
        now = time.time()
        msg = {
            "requestId": "rid-new-processing",
            # pending 에서 1시간 대기했지만 방금 processing 으로 넘어옴
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 3600)
            ),
            "processingStartedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 5)
            ),
        }
        client.get_messages.return_value = [(json.dumps(msg), msg)]
        reclaimer = _make_reclaimer(client, visibility=600)
        counts = reclaimer.reclaim_once(now_epoch=now)
        # processingStartedAt 이 fresh 이므로 reclaim 하지 않음
        assert counts["fresh"] == 1
        assert counts["reclaimed"] == 0

    def test_invalid_reclaimed_count_does_not_crash(self):
        """리뷰: reclaimedCount 가 None/비숫자여도 메시지 유실 금지."""
        client = _make_client()
        now = time.time()
        msg = {
            "requestId": "rid-bad",
            "processingStartedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 9999)
            ),
            "reclaimedCount": "bad",
        }
        client.get_messages.return_value = [(json.dumps(msg), msg)]
        reclaimer = _make_reclaimer(client, visibility=600)
        counts = reclaimer.reclaim_once(now_epoch=now)
        # prev_count 가 0 으로 방어 → reclaim 1 로 정상 처리
        assert counts["reclaimed"] == 1


class TestDlqResilience:
    """리뷰: LREM 이후 DLQ push 실패에도 reclaimer 가 계속 동작해야 한다."""

    def test_dlq_push_failure_does_not_crash_max_reclaim_branch(self):
        client = _make_client()
        client.push_to_failed.side_effect = Exception("redis down")
        now = time.time()
        poison = {
            "requestId": "rid-poison",
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 9999)
            ),
            "reclaimedCount": 3,
        }
        client.get_messages.return_value = [(json.dumps(poison), poison)]
        reclaimer = _make_reclaimer(client, visibility=600, max_reclaims=3)
        # 예외 없이 반환, dlq 카운트는 증가하지 않음 (DLQ push 실패)
        counts = reclaimer.reclaim_once(now_epoch=now)
        assert counts["dlq"] == 0
        client.push_to_failed.assert_called_once()

    def test_dlq_push_failure_on_corrupt_json_does_not_crash(self):
        client = _make_client()
        client.push_to_failed.side_effect = Exception("redis down")
        bad_parsed = {"_raw": "garbage", "_error": "JSONDecodeError"}
        client.get_messages.return_value = [("garbage", bad_parsed)]
        reclaimer = _make_reclaimer(client)
        counts = reclaimer.reclaim_once(now_epoch=time.time())
        assert counts["dlq"] == 0
        client.push_to_failed.assert_called_once()


class TestMarkFailedResultGuardBeforeReenqueue:
    """리뷰(공식 Django 근거): SELECT-then-UPDATE race 회피 위해 mark_failed 반환값 우선.
    docs: https://docs.djangoproject.com/en/5.2/ref/models/querysets/#update
    """

    def test_mark_failed_succeeds_reenqueues_without_is_terminal_check(self):
        """전이 성공 시: SELECT 없이 바로 re-enqueue (race 없음 확정)."""
        client = _make_client()
        now = time.time()
        stale = {
            "requestId": "rid-normal",
            "userId": 2,
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 1000)
            ),
            "reclaimedCount": 0,
            "retryCount": 1,
        }
        client.get_messages.return_value = [(json.dumps(stale), stale)]
        reclaimer = _make_reclaimer(client, visibility=600)
        lifecycle_stub = MagicMock()
        lifecycle_stub.mark_failed.return_value = MagicMock()  # 전이 성공
        reclaimer._lifecycle = lifecycle_stub

        counts = reclaimer.reclaim_once(now_epoch=now)

        # 성공 시 is_terminal 은 호출되지 않아야 함 (불필요한 SELECT 제거)
        client.enqueue_message.assert_called_once()
        lifecycle_stub.mark_failed.assert_called_once()
        lifecycle_stub.is_terminal.assert_not_called()
        assert counts["reclaimed"] == 1
        assert counts["dlq"] == 0

    def test_mark_failed_rejected_and_terminal_goes_to_dlq(self):
        """전이 거부 + terminal: 완료된 요청 중복 처리 방지 위해 DLQ 대피."""
        client = _make_client()
        now = time.time()
        stale = {
            "requestId": "rid-terminal",
            "userId": 1,
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 1000)
            ),
            "reclaimedCount": 0,
            "retryCount": 1,
        }
        client.get_messages.return_value = [(json.dumps(stale), stale)]
        reclaimer = _make_reclaimer(client, visibility=600)
        lifecycle_stub = MagicMock()
        lifecycle_stub.mark_failed.return_value = None  # 전이 거부
        lifecycle_stub.is_terminal.return_value = True  # SUCCESS/DLQ 확정
        reclaimer._lifecycle = lifecycle_stub

        counts = reclaimer.reclaim_once(now_epoch=now)

        client.enqueue_message.assert_not_called()
        client.push_to_failed.assert_called_once()
        lifecycle_stub.mark_failed.assert_called_once()
        lifecycle_stub.is_terminal.assert_called_once()
        assert counts["reclaimed"] == 0
        assert counts["dlq"] == 1

    def test_mark_failed_rejected_but_non_terminal_still_reenqueues(self):
        """전이 거부 + non-terminal (row missing 등): external producer 호환 재투입."""
        client = _make_client()
        now = time.time()
        stale = {
            "requestId": "rid-missing",
            "userId": 3,
            "enqueuedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 1000)
            ),
            "reclaimedCount": 0,
            "retryCount": 1,
        }
        client.get_messages.return_value = [(json.dumps(stale), stale)]
        reclaimer = _make_reclaimer(client, visibility=600)
        lifecycle_stub = MagicMock()
        lifecycle_stub.mark_failed.return_value = None
        lifecycle_stub.is_terminal.return_value = (
            False  # row 없음/QUEUED/FAILED
        )
        reclaimer._lifecycle = lifecycle_stub

        counts = reclaimer.reclaim_once(now_epoch=now)

        client.enqueue_message.assert_called_once()
        client.push_to_failed.assert_not_called()
        assert counts["reclaimed"] == 1
        assert counts["dlq"] == 0


class TestLoop:
    def test_loop_stops_when_shutdown_event_set(self):
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
