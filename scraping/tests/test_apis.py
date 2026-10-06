from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from scraping.apis import fetch_velog_posts
from scraping.reporting import SOURCE_VELOG_API


def _mock_session(payload: dict) -> MagicMock:
    """session.post 를 async context manager 로 흉내내는 mock."""
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=response)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    return session


class TestFetchVelogPosts:
    @pytest.mark.asyncio
    async def test_sends_query_requesting_views(self):
        """실제 전송 payload 의 쿼리가 views 를 요청하는지.

        통계는 이 쿼리의 views 로만 수집되므로, 필드가 빠지면 전량
        누락된다. process_user 테스트는 응답을 mock 하므로 이 구멍을
        잡지 못한다.
        """
        session = _mock_session({"data": {"posts": []}})

        await fetch_velog_posts(session, "tester", "at", "rt")

        sent_query = session.post.call_args.kwargs["json"]["query"]
        assert "views" in sent_query

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_malformed_response(self):
        """응답에 data 키가 없으면 예외 없이 빈 목록을 반환하는지.

        통계가 이 함수 하나에 전적으로 의존하게 되었으므로 실패
        경로가 조용히 터지지 않는지 고정한다.
        """
        session = _mock_session({"errors": [{"message": "boom"}]})

        result = await fetch_velog_posts(session, "tester", "at", "rt")

        assert result == []

    @pytest.mark.asyncio
    @patch("scraping.apis.capture_scraper_failure")
    @patch("scraping.apis.logger")
    async def test_network_failure_is_warning_and_reported_once(
        self, mock_logger, mock_capture
    ):
        """네트워크 실패는 warning 로그 + 보고 헬퍼 1회(source=velog-api)."""
        exc = aiohttp.ServerTimeoutError("slow")
        session = MagicMock()
        session.post = MagicMock(side_effect=exc)

        result = await fetch_velog_posts(session, "tester", "at", "rt")

        assert result == []
        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_not_called()
        mock_capture.assert_called_once_with(
            exc, source=SOURCE_VELOG_API, username="tester"
        )
