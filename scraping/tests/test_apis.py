from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from scraping.apis import (
    VelogFetchError,
    fetch_all_velog_posts,
    fetch_velog_posts,
    fetch_velog_user_chk,
)
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
    async def test_malformed_response_raises_with_cause(self):
        """응답에 data 키가 없으면 VelogFetchError(원인 체인)로 실패하는지.

        빈 목록([])은 "정상적으로 더 없음" 이므로 실패와 구분해야
        fetch_all 이 잘린 목록으로 비활성화를 돌리지 않는다.
        """
        session = _mock_session({"errors": [{"message": "boom"}]})

        with pytest.raises(VelogFetchError) as exc_info:
            await fetch_velog_posts(session, "tester", "at", "rt")

        assert isinstance(exc_info.value.__cause__, KeyError)

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

        with pytest.raises(VelogFetchError) as exc_info:
            await fetch_velog_posts(session, "tester", "at", "rt")

        assert exc_info.value.__cause__ is exc
        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_not_called()
        mock_capture.assert_called_once_with(
            exc, source=SOURCE_VELOG_API, username="tester"
        )


class TestFetchVelogUserChk:
    @pytest.mark.asyncio
    @patch("scraping.apis.capture_scraper_failure")
    @patch("scraping.apis.logger")
    async def test_failure_returns_empty_and_reports_once(
        self, mock_logger, mock_capture
    ):
        """user_chk 는 raise 하지 않고 ({}, {}) 를 돌려주므로 여기서 1회 보고."""
        exc = aiohttp.ServerTimeoutError("slow")
        session = MagicMock()
        session.post = MagicMock(side_effect=exc)

        result = await fetch_velog_user_chk(session, "at", "rt")

        assert result == ({}, {})
        mock_logger.warning.assert_called_once()
        mock_capture.assert_called_once_with(exc, source=SOURCE_VELOG_API)


class TestFetchAllVelogPosts:
    @pytest.mark.asyncio
    async def test_page_failure_propagates_instead_of_truncating(self):
        """2페이지 실패를 '마지막 페이지' 로 오인하면 잘린 목록으로
        sync_post_active_status 가 멀쩡한 글을 비활성화한다 → 예외로 전파."""
        page1 = [{"id": f"p{i}", "title": "t"} for i in range(50)]
        page1_response = MagicMock()
        page1_response.json = AsyncMock(
            return_value={"data": {"posts": page1}}
        )
        page1_cm = MagicMock()
        page1_cm.__aenter__ = AsyncMock(return_value=page1_response)
        page1_cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        page2_error = aiohttp.ServerTimeoutError("slow")
        session.post = MagicMock(side_effect=[page1_cm, page2_error])

        with patch("scraping.apis.capture_scraper_failure"):
            with pytest.raises(VelogFetchError) as exc_info:
                await fetch_all_velog_posts(session, "tester", "at", "rt")

        assert exc_info.value.__cause__ is page2_error

    @pytest.mark.asyncio
    async def test_genuine_empty_page_ends_pagination(self):
        """빈 목록은 정상 종료 — 실패가 아니다."""
        session = _mock_session({"data": {"posts": []}})

        result = await fetch_all_velog_posts(session, "tester", "at", "rt")

        assert result == []
