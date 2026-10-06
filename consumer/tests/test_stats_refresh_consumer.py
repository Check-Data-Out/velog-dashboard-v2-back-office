import signal
from unittest.mock import Mock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from tenacity import RetryError

from consumer.shutdown import get_shutdown_event
from consumer.stats_refresh_consumer import StatsRefreshConsumer


@patch("consumer.stats_refresh_consumer.MessageProcessor")
@patch("consumer.stats_refresh_consumer.RedisQueueClient")
class TestStatsRefreshConsumer:
    """Tests for StatsRefreshConsumer class."""

    def test_init(self, mock_redis_client_class, mock_processor_class) -> None:
        """Consumer 초기화 테스트."""
        consumer = StatsRefreshConsumer()

        assert consumer.redis_client is None
        assert consumer.running is False
        assert consumer.processing_message is False
        assert consumer.stats["processed"] == 0
        assert consumer.stats["succeeded"] == 0
        assert consumer.stats["failed"] == 0

    def test_setup_signal_handlers(
        self, mock_redis_client_class, mock_processor_class
    ) -> None:
        """시그널 핸들러 설정 테스트."""
        consumer = StatsRefreshConsumer()

        assert (
            signal.getsignal(signal.SIGTERM)
            == consumer._handle_shutdown_signal
        )
        assert (
            signal.getsignal(signal.SIGINT) == consumer._handle_shutdown_signal
        )

    def test_handle_shutdown_signal(
        self, mock_redis_client_class, mock_processor_class
    ) -> None:
        """시그널 핸들러는 플래그/Event 만 세우고 Redis 를 닫지 않는다.

        BLMOVE 대기 중 핸들러가 close 하면 main thread 가
        'I/O operation on closed file' 로 깨진다 (VD-BACKOFFICE-6Q).
        """
        consumer = StatsRefreshConsumer()
        consumer.redis_client = Mock()
        consumer.running = True

        consumer._handle_shutdown_signal(signal.SIGTERM, None)

        assert consumer.running is False
        # Event.set 은 핸들러 밖(스레드)에서 수행되므로 잠시 기다린다
        assert get_shutdown_event().wait(1)
        consumer.redis_client.close.assert_not_called()

    @patch("consumer.stats_refresh_consumer.start_healthz_server")
    @patch.object(StatsRefreshConsumer, "_start_reclaimer")
    @patch.object(StatsRefreshConsumer, "_consume_loop")
    def test_start_closes_redis_after_consume_loop(
        self,
        mock_loop,
        mock_start_reclaimer,
        mock_healthz,
        mock_redis_client_class,
        mock_processor_class,
    ) -> None:
        """start() 는 _consume_loop 가 반환한 뒤에 Redis 를 1회 닫는다."""
        mock_client = Mock()
        consumer = StatsRefreshConsumer(redis_client=mock_client)
        # 루프가 도는 동안에는 아직 닫히지 않았어야 한다 (상태 단언)
        mock_loop.side_effect = lambda: mock_client.close.assert_not_called()

        consumer.start()

        mock_loop.assert_called_once()
        mock_client.close.assert_called_once()

    @patch("consumer.stats_refresh_consumer.start_healthz_server")
    @patch.object(StatsRefreshConsumer, "_start_reclaimer")
    @patch.object(StatsRefreshConsumer, "_consume_loop")
    def test_start_skips_loop_when_shutdown_already_requested(
        self,
        mock_loop,
        mock_start_reclaimer,
        mock_healthz,
        mock_redis_client_class,
        mock_processor_class,
    ) -> None:
        """start 전에 종료 요청이 있었으면 루프에 들어가지 않는다."""
        consumer = StatsRefreshConsumer(redis_client=Mock())
        get_shutdown_event().set()

        consumer.start()

        mock_loop.assert_not_called()

    @patch("consumer.stats_refresh_consumer.start_healthz_server")
    @patch.object(StatsRefreshConsumer, "_start_reclaimer")
    @patch.object(StatsRefreshConsumer, "_consume_loop")
    def test_start_closes_redis_when_consume_loop_raises(
        self,
        mock_loop,
        mock_start_reclaimer,
        mock_healthz,
        mock_redis_client_class,
        mock_processor_class,
    ) -> None:
        """루프가 예외로 빠져나와도 Redis 는 닫힌다 (finally)."""
        mock_client = Mock()
        consumer = StatsRefreshConsumer(redis_client=mock_client)
        mock_loop.side_effect = RuntimeError("boom")

        with pytest.raises(SystemExit):
            consumer.start()

        mock_client.close.assert_called_once()

    @patch("consumer.stats_refresh_consumer.get_redis_client")
    def test_reconnect_skips_connect_when_shutdown_requested(
        self, mock_get_client, mock_redis_client_class, mock_processor_class
    ) -> None:
        """종료 요청 이후에는 연결 시도 없이 바로 RetryError 로 끝난다."""
        consumer = StatsRefreshConsumer(redis_client=Mock(spec=["close"]))
        consumer.request_shutdown()

        with pytest.raises(RetryError):
            consumer._reconnect_with_backoff()

        mock_get_client.assert_not_called()

    @patch("sentry_sdk.capture_exception")
    @patch("consumer.stats_refresh_consumer.logger")
    @patch("consumer.stats_refresh_consumer.get_redis_client")
    @patch("consumer.stats_refresh_consumer.start_healthz_server")
    @patch.object(StatsRefreshConsumer, "_start_reclaimer")
    def test_shutdown_during_reconnect_exits_loop_without_critical_or_capture(
        self,
        mock_start_reclaimer,
        mock_healthz,
        mock_get_client,
        mock_logger,
        mock_capture,
        mock_redis_client_class,
        mock_processor_class,
    ) -> None:
        """재연결 대기 중 SIGTERM 이 오면 critical/이벤트 없이 정상 종료한다.

        종료 후의 재연결 대기는 Event.wait 라 즉시 깨어나므로, 회귀 시에도
        30회 재시도가 긴 대기 없이 빠르게 실패한다.
        """
        mock_client = Mock(
            spec=["blocking_move_pending_to_processing", "close"]
        )
        mock_client.blocking_move_pending_to_processing.side_effect = (
            RedisConnectionError("down")
        )
        consumer = StatsRefreshConsumer(redis_client=mock_client)

        def fail_then_request_shutdown():
            consumer.request_shutdown()
            raise RedisConnectionError("still down")

        mock_get_client.side_effect = fail_then_request_shutdown

        consumer.start()  # SystemExit 없이 반환해야 한다

        assert mock_get_client.call_count == 1
        mock_logger.critical.assert_not_called()
        mock_capture.assert_not_called()
        mock_client.close.assert_called_once()

    @patch("sentry_sdk.capture_exception")
    @patch("consumer.stats_refresh_consumer.logger")
    @patch.object(StatsRefreshConsumer, "_reconnect_with_backoff")
    def test_reconnect_exhausted_is_single_critical_without_capture(
        self,
        mock_reconnect,
        mock_logger,
        mock_capture,
        mock_redis_client_class,
        mock_processor_class,
    ) -> None:
        """재연결 소진은 critical(exc_info) 1회 + exit(1), capture 는 없다 (R2')."""
        mock_client = Mock()
        mock_client.blocking_move_pending_to_processing.side_effect = (
            RedisConnectionError("down")
        )
        consumer = StatsRefreshConsumer(redis_client=mock_client)
        consumer.redis_client = mock_client
        consumer.running = True
        mock_reconnect.side_effect = RetryError(Mock())

        with pytest.raises(SystemExit):
            consumer._consume_loop()

        mock_logger.critical.assert_called_once()
        assert mock_logger.critical.call_args.kwargs.get("exc_info")
        mock_capture.assert_not_called()

    def test_process_message_success(
        self, mock_redis_client_class, mock_processor_class, sample_message
    ) -> None:
        """메시지 처리 성공 — BLMOVE 기반, push_to_processing 은 호출되지 않음."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.message_processor.process_with_retry = Mock(return_value=True)

        consumer._process_message(sample_message)

        assert consumer.stats["processed"] == 1
        assert consumer.stats["succeeded"] == 1
        assert consumer.stats["failed"] == 0
        # processing 큐 제거는 remove_message(queue, raw) 로 수행
        mock_redis_client.remove_message.assert_called_once()
        remove_args = mock_redis_client.remove_message.call_args[0]
        assert (
            remove_args[0]
            == consumer.redis_config.QUEUE_STATS_REFRESH_PROCESSING
        )
        # push_to_processing 은 더 이상 호출되지 않음
        mock_redis_client.push_to_processing.assert_not_called()

    def test_process_message_failure(
        self, mock_redis_client_class, mock_processor_class, sample_message
    ) -> None:
        """메시지 처리 실패 테스트 (BLMOVE 이후 → DLQ push + processing 제거)."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.message_processor.process_with_retry = Mock(
            return_value=False
        )

        consumer._process_message(sample_message)

        assert consumer.stats["processed"] == 1
        assert consumer.stats["succeeded"] == 0
        assert consumer.stats["failed"] == 1
        mock_redis_client.push_to_failed.assert_called_once_with(
            sample_message
        )
        mock_redis_client.remove_message.assert_called_once()

    def test_mark_processing_rejected_and_terminal_drops_message(
        self, mock_redis_client_class, mock_processor_class, sample_message
    ) -> None:
        """mark_processing 이 None + 현재 terminal 이면 processing 만 LREM + skip.

        Redis 에 중복 남은 메시지로 이미 완료된 요청이 재실행되는 것을 막는다.
        """
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client

        # lifecycle: mark_processing → None (거부), is_terminal → True
        lifecycle_stub = Mock()
        lifecycle_stub.mark_processing.return_value = None
        lifecycle_stub.is_terminal.return_value = True
        consumer._lifecycle = lifecycle_stub

        consumer.message_processor.process_with_retry = Mock(return_value=True)

        consumer._process_message(sample_message, raw_str="orig-raw")

        # 실제 처리는 호출되지 않아야 함
        consumer.message_processor.process_with_retry.assert_not_called()
        # processing 큐에서만 제거
        mock_redis_client.remove_message.assert_called_once()
        args = mock_redis_client.remove_message.call_args[0]
        assert args[0] == consumer.redis_config.QUEUE_STATS_REFRESH_PROCESSING
        assert args[1] == "orig-raw"
        # DLQ 로도 보내지 않음
        mock_redis_client.push_to_failed.assert_not_called()
        lifecycle_stub.is_terminal.assert_called_once()

    def test_mark_processing_rejected_but_not_terminal_still_processes(
        self, mock_redis_client_class, mock_processor_class, sample_message
    ) -> None:
        """mark_processing None + non-terminal (row missing) 은 기존처럼 처리 진행.

        external producer 호환을 위해 drop 하지 않는다.
        """
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client

        lifecycle_stub = Mock()
        lifecycle_stub.mark_processing.return_value = None
        lifecycle_stub.is_terminal.return_value = False  # row missing 등
        consumer._lifecycle = lifecycle_stub

        consumer.message_processor.process_with_retry = Mock(return_value=True)

        consumer._process_message(sample_message, raw_str="orig-raw")

        consumer.message_processor.process_with_retry.assert_called_once()
        assert consumer.stats["succeeded"] == 1

    def test_get_stats_summary(
        self, mock_redis_client_class, mock_processor_class
    ) -> None:
        """통계 요약 조회 테스트."""
        consumer = StatsRefreshConsumer()
        consumer.stats["processed"] = 10
        consumer.stats["succeeded"] = 8
        consumer.stats["failed"] = 2

        summary = consumer._get_stats_summary()

        assert "processed=10" in summary
        assert "succeeded=8" in summary
        assert "failed=2" in summary
        assert "uptime=" in summary

    def test_shutdown_is_idempotent_after_signal_cleared_running(
        self, mock_redis_client_class, mock_processor_class
    ) -> None:
        """핸들러가 running=False 를 먼저 세운 뒤에도 shutdown 은 close 를 정확히 1회."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.running = False  # 시그널 핸들러가 먼저 내린 상태

        consumer.shutdown()
        consumer.shutdown()

        assert consumer.running is False
        assert get_shutdown_event().is_set()
        mock_redis_client.close.assert_called_once()
