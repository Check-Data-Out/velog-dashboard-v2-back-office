import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.db import transaction

from posts.models import Post
from scraping.main import Scraper
from users.models import User


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
    async def test_update_old_tokens_success(
        self, mock_aes, scraper, user
    ) -> None:
        """토큰 업데이트 성공 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = (
            lambda token: f"decrypted-{token}"
        )
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

        new_tokens = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_tokens(
                user, mock_encryption, new_tokens
            )

        assert result is True
        mock_asave.assert_called_once()
        assert user.access_token == "encrypted-new-access-token"
        assert user.refresh_token == "encrypted-new-refresh-token"
        mock_encryption.decrypt.assert_any_call("encrypted-access-token")
        mock_encryption.decrypt.assert_any_call("encrypted-refresh-token")

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_tokens_no_change(self, mock_aes, scraper, user):
        """토큰 업데이트 없음 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = lambda token: token
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

        new_tokens = {
            "access_token": "encrypted-access-token",
            "refresh_token": "encrypted-refresh-token",
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_tokens(
                user, mock_encryption, new_tokens
            )

        assert result is False
        mock_asave.assert_not_called()

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_tokens_expired_failure(
        self, mock_aes, scraper, user
    ):
        """토큰이 만료되었을 때 업데이트 실패 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = (
            lambda token: f"decrypted-{token}"
        )
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

        new_tokens = {
            "access_token": "decrypted-encrypted-access-token",
            "refresh_token": "decrypted-encrypted-refresh-token",
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_tokens(
                user, mock_encryption, new_tokens
            )

        assert result is False
        mock_asave.assert_not_called()

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_tokens_with_mocked_decryption_failure(
        self, mock_aes, scraper, user
    ):
        """복호화가 제대로 되지 않았을 경우 업데이트 실패 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = lambda token: None
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

        new_tokens = {
            "access_token": "valid_token",
            "refresh_token": "valid_token",
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_tokens(
                user, mock_encryption, new_tokens
            )

        assert result is False
        mock_asave.assert_not_called()

    @patch("scraping.main.Post.objects.bulk_create", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_bulk_insert_posts_success(
        self, mock_bulk_create, scraper, user
    ):
        """Post 객체 배치 분할 삽입 성공 테스트"""
        posts_data = [
            {
                "id": f"post-{i}",
                "title": f"Title {i}",
                "url_slug": f"slug-{i}",
                "released_at": "2025-03-07",
            }
            for i in range(50)
        ]

        result = await scraper.bulk_insert_posts(
            user, posts_data, batch_size=10
        )

        assert result is True
        mock_bulk_create.assert_called()
        assert mock_bulk_create.call_count == 5

    @patch(
        "scraping.main.Post.objects.bulk_create",
        side_effect=Exception("DB 에러"),
    )
    @pytest.mark.asyncio
    async def test_bulk_insert_posts_failure(
        self, mock_bulk_create, scraper, user
    ):
        """Post 객체 배치 분할 삽입 실패 테스트"""
        posts_data = [
            {
                "id": f"post-{i}",
                "title": f"Title {i}",
                "url_slug": f"slug-{i}",
                "released_at": "2025-03-07",
            }
            for i in range(10)
        ]

        result = await scraper.bulk_insert_posts(
            user, posts_data, batch_size=5
        )

        assert result is False
        mock_bulk_create.assert_called()

    @pytest.mark.asyncio
    async def test_update_daily_statistics_success(self, scraper):
        """데일리 통계 업데이트 또는 생성 성공 테스트"""
        post_data = {"id": "post-123"}
        stats_data = {"data": {"getStats": {"total": 100}}, "likes": 5}

        with patch(
            "scraping.main.sync_to_async", new_callable=MagicMock
        ) as mock_sync_to_async:
            mock_async_func = AsyncMock()
            mock_sync_to_async.return_value = mock_async_func

            await scraper.update_daily_statistics(post_data, stats_data)

            mock_sync_to_async.assert_called()
            mock_async_func.assert_called_once()

            for call_args in mock_sync_to_async.call_args_list:
                args, kwargs = call_args

                assert callable(args[0])

                if kwargs:
                    assert "post-123" in str(kwargs.get("post_data", ""))
                    assert 100 in str(kwargs.get("stats_data", ""))

    @patch("scraping.main.sync_to_async", new_callable=MagicMock)
    @pytest.mark.asyncio
    async def test_update_daily_statistics_exception(
        self, mock_sync_to_async, scraper
    ):
        """데일리 통계 업데이트 실패 테스트"""
        post_data = {"id": "post-123"}
        stats_data = {"data": {"getStats": {"total": 100}}, "likes": 5}

        mock_async_func = AsyncMock(side_effect=Exception("Database error"))
        mock_sync_to_async.return_value = mock_async_func

        try:
            await scraper.update_daily_statistics(post_data, stats_data)
        except Exception:
            pass

        mock_sync_to_async.assert_called()
        mock_async_func.assert_called_once()

    @patch("scraping.main.fetch_post_stats")
    @pytest.mark.asyncio
    async def test_fetch_post_stats_limited_success(self, mock_fetch, scraper):
        """fetch_post_stats 성공 테스트"""
        mock_fetch.side_effect = [
            None,
            None,
            {"data": {"getStats": {"total": 100}}},
        ]

        result = await scraper.fetch_post_stats_limited(
            "post-123", "token-1", "token-2"
        )

        assert result is not None
        mock_fetch.assert_called()
        assert mock_fetch.call_count == 3

        for call_args in mock_fetch.call_args_list:
            args, kwargs = call_args
            assert "post-123" in str(args) or "post-123" in str(kwargs)
            assert (
                "token-1" in str(args)
                or "token-1" in str(kwargs)
                or "token-2" in str(args)
                or "token-2" in str(kwargs)
            )

    @patch("scraping.main.fetch_post_stats")
    @pytest.mark.asyncio
    async def test_fetch_post_stats_limited_max_retries(
        self, mock_fetch, scraper
    ):
        """최대 재시도 횟수 초과 테스트"""
        mock_fetch.return_value = None

        result = await scraper.fetch_post_stats_limited(
            "post-123", "token-1", "token-2"
        )

        assert result is None
        assert mock_fetch.call_count >= 3

    @patch("scraping.main.fetch_post_stats", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_fetch_post_stats_limited_failure(self, mock_fetch, scraper):
        """fetch_post_stats 실패 테스트"""
        mock_fetch.side_effect = [None, None, None]

        result = await scraper.fetch_post_stats_limited(
            "post-123", "token-1", "token-2"
        )

        assert result is None
        assert mock_fetch.call_count == 3

    @patch("scraping.main.fetch_velog_user_chk")
    @patch("scraping.main.fetch_all_velog_posts")
    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_process_user_success(
        self, mock_aes, mock_fetch_posts, mock_fetch_user_chk, scraper, user
    ):
        """유저 데이터 전체 처리 성공 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = (
            lambda token: f"decrypted-{token}"
        )
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

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

    @patch("scraping.main.transaction.atomic")
    @pytest.mark.django_db(transaction=True)
    async def test_process_user_failure_rollback(
        self, mock_atomic, scraper, user
    ):
        """유저 데이터 처리 실패 시 롤백 확인 테스트"""
        mock_session = AsyncMock()
        mock_atomic.side_effect = (
            transaction.atomic
        )  # 실제 트랜잭션을 패치한 형태로 유지

        with patch(
            "scraping.main.fetch_velog_user_chk",
            side_effect=Exception("Failed to fetch user data"),
        ):
            try:
                await scraper.process_user(user, mock_session)
            except Exception:
                pass

        assert Post.objects.filter(user=user).count() == 0

    @pytest.mark.django_db(transaction=True)
    async def test_process_user_partial_failure_rollback(self, scraper, user):
        """통계 업데이트 중 실패 시 롤백 확인 테스트"""
        mock_session = AsyncMock()

        with patch(
            "scraping.main.fetch_post_stats_limited",
            side_effect=Exception("Failed to fetch post stats limited"),
        ):
            try:
                async with transaction.atomic():
                    await scraper.process_user(user, mock_session)
            except Exception:
                pass

        assert Post.objects.filter(user=user).exists()
        assert not any(
            post.statistics for post in Post.objects.filter(user=user)
        )
