import signal
from unittest.mock import Mock, patch

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
        """Shutdown 시그널 처리 테스트."""
        consumer = StatsRefreshConsumer()
        consumer.running = True

        consumer._handle_shutdown_signal(signal.SIGTERM, None)

        assert consumer.running is False

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

    @patch("consumer.stats_refresh_consumer.time.sleep")
    def test_shutdown_graceful(
        self, mock_sleep, mock_redis_client_class, mock_processor_class
    ) -> None:
        """Graceful shutdown 테스트."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.running = True
        consumer.processing_message = False

        consumer.shutdown()

        assert consumer.running is False
        mock_redis_client.close.assert_called_once()

    @patch("consumer.stats_refresh_consumer.time.sleep")
    def test_shutdown_with_processing_message(
        self, mock_sleep, mock_redis_client_class, mock_processor_class
    ) -> None:
        """메시지 처리 중 shutdown 테스트."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.running = True
        consumer.processing_message = True

        def sleep_side_effect(duration):
            consumer.processing_message = False

        mock_sleep.side_effect = sleep_side_effect

        consumer.shutdown()

        assert consumer.running is False
        mock_redis_client.close.assert_called_once()

    def test_shutdown_already_stopped(
        self, mock_redis_client_class, mock_processor_class
    ) -> None:
        """이미 중지된 상태에서 shutdown 테스트."""
        consumer = StatsRefreshConsumer()
        consumer.running = False

        consumer.shutdown()

        assert consumer.running is False
