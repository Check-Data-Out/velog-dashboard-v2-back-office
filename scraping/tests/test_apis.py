from unittest.mock import AsyncMock, MagicMock

import pytest

from scraping.apis import fetch_velog_posts


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
    async def test_returns_posts_from_response(self):
        """응답의 posts 배열을 그대로 반환하는지."""
        posts = [{"id": "p1", "views": 10}]
        session = _mock_session({"data": {"posts": posts}})

        result = await fetch_velog_posts(session, "tester", "at", "rt")

        assert result == posts
