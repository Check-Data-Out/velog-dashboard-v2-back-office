from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uuid

from users.models import User
from scraping.main import Scraper


class TestScraper:
    @pytest.fixture
    def scraper(self):
        """Scraper 인스턴스 생성"""
        return Scraper(group_range=range(1, 10), max_connections=10)

    @pytest.fixture
    def user(self, db):
        """테스트용 User 객체 생성"""
        return User.objects.create(
            velog_uuid=uuid.uuid4(),
            access_token="encrypted-access-token",
            refresh_token="encrypted-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_tokens(self, mock_aes, scraper, user):
        """토큰 만료로 인한 토큰 업데이트 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = lambda token: f"decrypted-{token}"
        mock_encryption.encrypt.side_effect = lambda token: f"encrypted-{token}"

        new_tokens = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_tokens(user, mock_encryption, new_tokens)

        assert result is True
        mock_asave.assert_called_once()
        assert user.access_token == "encrypted-new-access-token"
        assert user.refresh_token == "encrypted-new-refresh-token"

    @patch("scraping.main.Post.objects.bulk_create", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_bulk_insert_posts(self, mock_bulk_create, scraper, user):
        """Post 객체를 일정 크기의 배치로 나눠서 삽입 테스트"""
        posts_data = [
            {
                "id": f"post-{i}",
                "title": f"Title {i}",
                "url_slug": f"slug-{i}",
                "released_at": "2025-03-07",
            }
            for i in range(50)
        ]

        result = await scraper.bulk_insert_posts(user, posts_data, batch_size=10)

        assert result is True
        mock_bulk_create.assert_called()
        assert mock_bulk_create.call_count == 5

    @patch("scraping.main.sync_to_async", new_callable=MagicMock)
    @pytest.mark.asyncio
    async def test_update_daily_statistics(self, mock_sync_to_async, scraper):
        """PostDailyStatistics 업데이트 또는 생성 테스트"""
        post_data = {"id": "post-123"}
        stats_data = {"data": {"getStats": {"total": 100}}, "likes": 5}

        mock_sync_to_async.return_value = AsyncMock()

        await scraper.update_daily_statistics(post_data, stats_data)

        mock_sync_to_async.assert_called()

    @patch("scraping.main.fetch_post_stats")
    @pytest.mark.asyncio
    async def test_fetch_post_stats_limited(self, mock_fetch, scraper):
        """세마포어를 적용한 fetch_post_stats + 엄격한 재시도 로직 추가 테스트"""
        mock_fetch.side_effect = [None, None, {"data": {"getStats": {"total": 100}}}]

        result = await scraper.fetch_post_stats_limited(
            "post-123", "token-1", "token-2"
        )

        assert result is not None
        mock_fetch.assert_called()
        assert mock_fetch.call_count == 3

    @patch("scraping.main.fetch_velog_user_chk")
    @patch("scraping.main.fetch_all_velog_posts")
    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_process_user(
        self, mock_aes, mock_fetch_posts, mock_fetch_user_chk, scraper, user
    ):
        """scraping 메인 비즈니스로직, 유저 데이터를 전체 처리 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = lambda token: f"decrypted-{token}"
        mock_encryption.encrypt.side_effect = lambda token: f"encrypted-{token}"

        mock_fetch_user_chk.return_value = (
            {"access_token": "new-token"},
            {"data": {"currentUser": {"username": "testuser"}}},
        )
        mock_fetch_posts.return_value = []

        with patch.object(
            scraper, "update_old_tokens", new_callable=AsyncMock
        ) as mock_update_tokens:
            await scraper.process_user(user, MagicMock())

        mock_update_tokens.assert_called_once()
