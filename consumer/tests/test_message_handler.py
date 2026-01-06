from unittest.mock import AsyncMock, Mock, patch

import pytest

from consumer.message_handler import (
    MessageProcessor,
    StatsRefreshMessageHandler,
)


class TestStatsRefreshMessageHandler:
    """Tests for StatsRefreshMessageHandler class."""

    @pytest.mark.asyncio
    @patch("consumer.message_handler.ScraperTargetUser")
    async def test_process_message_success(
        self, mock_scraper_class, sample_message
    ) -> None:
        """메시지 처리 성공 테스트."""
        mock_scraper = Mock()
        mock_scraper.run = AsyncMock()
        mock_scraper_class.return_value = mock_scraper

        handler = StatsRefreshMessageHandler()
        await handler.process_message(sample_message)

        mock_scraper_class.assert_called_once_with(
            user_pk_list=[123], max_connections=40
        )
        mock_scraper.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_missing_user_id(
        self, invalid_message
    ) -> None:
        """userId가 없는 메시지 처리 실패 테스트."""
        handler = StatsRefreshMessageHandler()

        with pytest.raises(
            ValueError, match="Message missing required field: userId"
        ):
            await handler.process_message(invalid_message)

    @pytest.mark.asyncio
    @patch("consumer.message_handler.ScraperTargetUser")
    async def test_process_message_scraper_failure(
        self, mock_scraper_class, sample_message
    ) -> None:
        """Scraper 실행 실패 테스트."""
        mock_scraper = Mock()
        mock_scraper.run = AsyncMock(side_effect=Exception("Scraper error"))
        mock_scraper_class.return_value = mock_scraper

        handler = StatsRefreshMessageHandler()

        with pytest.raises(Exception, match="Scraper error"):
            await handler.process_message(sample_message)

    @patch("consumer.message_handler.asyncio.run")
    @patch("consumer.message_handler.ScraperTargetUser")
    def test_handle_message_sync(
        self, mock_scraper_class, mock_asyncio_run, sample_message
    ) -> None:
        """동기 wrapper 함수 테스트."""
        mock_scraper = Mock()
        mock_scraper.run = AsyncMock()
        mock_scraper_class.return_value = mock_scraper

        handler = StatsRefreshMessageHandler()
        handler.handle_message_sync(sample_message)

        mock_asyncio_run.assert_called_once()


class TestMessageProcessor:
    """Tests for MessageProcessor class."""

    @patch("consumer.message_handler.StatsRefreshMessageHandler")
    def test_process_with_retry_success(
        self, mock_handler_class, sample_message
    ) -> None:
        """재시도 없이 첫 번째 시도에서 성공 테스트."""
        mock_handler = Mock()
        mock_handler.handle_message_sync = Mock()
        mock_handler_class.return_value = mock_handler

        processor = MessageProcessor()
        processor.handler = mock_handler

        result = processor.process_with_retry(sample_message)

        assert result is True
        mock_handler.handle_message_sync.assert_called_once()

    @patch("consumer.message_handler.StatsRefreshMessageHandler")
    @patch("consumer.message_handler.time.sleep")
    def test_process_with_retry_failure(
        self, mock_sleep, mock_handler_class, sample_message
    ) -> None:
        """모든 재시도 후 실패 테스트."""
        mock_handler = Mock()
        mock_handler.handle_message_sync = Mock(
            side_effect=Exception("Processing error")
        )
        mock_handler_class.return_value = mock_handler

        processor = MessageProcessor()
        processor.handler = mock_handler

        result = processor.process_with_retry(sample_message)

        assert result is False
        assert mock_handler.handle_message_sync.call_count == 3  # MAX_RETRIES
        assert mock_sleep.call_count == 2  # 3회 시도 중 마지막 제외 2번 sleep

    @patch("consumer.message_handler.StatsRefreshMessageHandler")
    def test_process_with_retry_invalid_message(
        self, mock_handler_class, sample_message
    ) -> None:
        """잘못된 메시지 형식으로 재시도 없이 실패 테스트."""
        mock_handler = Mock()
        mock_handler.handle_message_sync = Mock(
            side_effect=ValueError("Invalid")
        )
        mock_handler_class.return_value = mock_handler

        processor = MessageProcessor()
        processor.handler = mock_handler

        result = processor.process_with_retry(sample_message)

        assert result is False
        mock_handler.handle_message_sync.assert_called_once()  # 재시도 없음

    @patch("consumer.message_handler.StatsRefreshMessageHandler")
    @patch("consumer.message_handler.time.sleep")
    def test_process_with_retry_success_on_second_attempt(
        self, mock_sleep, mock_handler_class, sample_message
    ) -> None:
        """두 번째 시도에서 성공 테스트."""
        mock_handler = Mock()
        # 첫 번째는 실패, 두 번째는 성공
        mock_handler.handle_message_sync = Mock(
            side_effect=[Exception("First fail"), None]
        )
        mock_handler_class.return_value = mock_handler

        processor = MessageProcessor()
        processor.handler = mock_handler

        result = processor.process_with_retry(sample_message)

        assert result is True
        assert mock_handler.handle_message_sync.call_count == 2
        mock_sleep.assert_called_once()  # 첫 번째 실패 후 1번 sleep
