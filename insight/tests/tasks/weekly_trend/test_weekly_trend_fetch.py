from unittest.mock import patch

import pytest


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyTrendFetch:
    async def test_fetch_data_when_fail_get_post_detail(
        self, analyzer, mock_context
    ):
        """게시글 본문 조회 실패 시, body 없이 기본 데이터로 대체되는지 테스트"""
        mock_context.velog_client.get_post.side_effect = Exception(
            "fetch error"
        )

        with patch.object(analyzer, "logger") as mock_logger:
            result = await analyzer._fetch_data(mock_context)

        assert len(result) == 1
        assert result[0].body == ""
        mock_logger.warning.assert_called()

    async def test_fetch_data_failure_with_empty_body(
        self, analyzer, mock_context
    ):
        """게시글 본문이 비었을 경우, warning 로그 출력 확인 테스트"""
        mock_context.velog_client.get_post.return_value.body = ""

        with patch.object(analyzer, "logger") as mock_logger:
            result = await analyzer._fetch_data(mock_context)

        assert result[0].body == ""
        mock_logger.warning.assert_called_with(
            "Post %s has empty body", "abc123"
        )
