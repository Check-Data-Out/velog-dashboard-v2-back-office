"""Tests for stats refresh consumer."""

import signal
from unittest.mock import Mock, patch

from consumer.stats_refresh_consumer import StatsRefreshConsumer


class TestStatsRefreshConsumer:
    """Tests for StatsRefreshConsumer class."""

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    def test_init(self, mock_redis_client_class) -> None:
        """Consumer 초기화 테스트."""
        consumer = StatsRefreshConsumer()

        assert consumer.redis_client is None
        assert consumer.running is False
        assert consumer.processing_message is False
        assert consumer.stats["processed"] == 0
        assert consumer.stats["succeeded"] == 0
        assert consumer.stats["failed"] == 0

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    def test_setup_signal_handlers(self, mock_redis_client_class) -> None:
        """시그널 핸들러 설정 테스트."""
        consumer = StatsRefreshConsumer()

        # 시그널 핸들러가 설정되었는지 확인
        assert (
            signal.getsignal(signal.SIGTERM)
            == consumer._handle_shutdown_signal
        )
        assert (
            signal.getsignal(signal.SIGINT) == consumer._handle_shutdown_signal
        )

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    def test_handle_shutdown_signal(self, mock_redis_client_class) -> None:
        """Shutdown 시그널 처리 테스트."""
        consumer = StatsRefreshConsumer()
        consumer.running = True

        consumer._handle_shutdown_signal(signal.SIGTERM, None)

        assert consumer.running is False

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    def test_process_message_success(
        self, mock_redis_client_class, sample_message
    ) -> None:
        """메시지 처리 성공 테스트."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.message_processor.process_with_retry = Mock(return_value=True)  # type: ignore

        consumer._process_message(sample_message)

        assert consumer.stats["processed"] == 1
        assert consumer.stats["succeeded"] == 1
        assert consumer.stats["failed"] == 0
        mock_redis_client.push_to_processing.assert_called_once_with(
            sample_message
        )
        mock_redis_client.remove_from_processing.assert_called_once_with(
            sample_message
        )

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    def test_process_message_failure(
        self, mock_redis_client_class, sample_message
    ) -> None:
        """메시지 처리 실패 테스트."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.message_processor.process_with_retry = Mock(  # type: ignore
            return_value=False
        )

        consumer._process_message(sample_message)

        assert consumer.stats["processed"] == 1
        assert consumer.stats["succeeded"] == 0
        assert consumer.stats["failed"] == 1
        mock_redis_client.push_to_failed.assert_called_once_with(
            sample_message
        )

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    def test_get_stats_summary(self, mock_redis_client_class) -> None:
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

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    @patch("consumer.stats_refresh_consumer.time.sleep")
    def test_shutdown_graceful(
        self, mock_sleep, mock_redis_client_class
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

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    @patch("consumer.stats_refresh_consumer.time.sleep")
    def test_shutdown_with_processing_message(
        self, mock_sleep, mock_redis_client_class
    ) -> None:
        """메시지 처리 중 shutdown 테스트."""
        mock_redis_client = Mock()
        mock_redis_client_class.return_value = mock_redis_client

        consumer = StatsRefreshConsumer()
        consumer.redis_client = mock_redis_client
        consumer.running = True
        consumer.processing_message = True

        # processing_message를 False로 변경하는 side effect
        def sleep_side_effect(duration):
            consumer.processing_message = False

        mock_sleep.side_effect = sleep_side_effect

        consumer.shutdown()

        assert consumer.running is False
        mock_redis_client.close.assert_called_once()

    @patch("consumer.stats_refresh_consumer.RedisQueueClient")
    def test_shutdown_already_stopped(self, mock_redis_client_class) -> None:
        """이미 중지된 상태에서 shutdown 테스트."""
        consumer = StatsRefreshConsumer()
        consumer.running = False

        # Should not raise any errors
        consumer.shutdown()

        assert consumer.running is False
