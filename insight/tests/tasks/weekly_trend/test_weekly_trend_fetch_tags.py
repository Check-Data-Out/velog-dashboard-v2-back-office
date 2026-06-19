from unittest.mock import patch

import pytest


@pytest.mark.asyncio
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyTrendFetchTags:
    async def test_fetch_data_preserves_tags(self, analyzer, mock_context):
        """get_post detail 의 tags 가 TrendingPostData 에 보존된다 (S4 신호 선결)."""
        with patch.object(analyzer, "logger"):
            result = await analyzer._fetch_data(mock_context)

        assert result[0].tags == ["python", "django"]

    async def test_fetch_data_tags_empty_on_detail_failure(
        self, analyzer, mock_context
    ):
        """본문 조회 실패 시 tags 는 빈 리스트로 대체된다."""
        mock_context.velog_client.get_post.side_effect = Exception(
            "fetch error"
        )

        with patch.object(analyzer, "logger"):
            result = await analyzer._fetch_data(mock_context)

        assert result[0].tags == []

    async def test_fetch_data_tags_empty_when_detail_tags_none(
        self, analyzer, mock_context
    ):
        """detail.tags 가 None 이면 빈 리스트로 대체된다."""
        mock_context.velog_client.get_post.return_value.tags = None

        with patch.object(analyzer, "logger"):
            result = await analyzer._fetch_data(mock_context)

        assert result[0].tags == []
