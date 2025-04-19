import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from scraping.main import Scraper
from users.models import User
from utils.utils import get_local_now


class TestScraperTokenAndProcessing:
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
    async def test_update_old_tokens_no_change(
        self, mock_aes, scraper, user
    ) -> None:
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

    @patch("scraping.main.fetch_post_stats")
    @pytest.mark.asyncio
    async def test_fetch_post_stats_limited_success(self, mock_fetch, scraper):
        """fetch_post_stats 성공 테스트"""
        mock_fetch.return_value = {"data": {"getStats": {"total": 100}}}

        result = await scraper.fetch_post_stats_limited(
            "post-123", "token-1", "token-2"
        )

        assert result is not None
        assert result["data"]["getStats"]["total"] == 100
        mock_fetch.assert_called_once_with("post-123", "token-1", "token-2")

    @patch("scraping.main.fetch_post_stats")
    @pytest.mark.asyncio
    async def test_fetch_post_stats_limited_retry_success(
        self, mock_fetch, scraper
    ):
        """fetch_post_stats 재시도 성공 테스트"""
        mock_fetch.side_effect = [
            None,  # 첫 번째 시도 실패
            {"data": {"getStats": {"total": 100}}},  # 두 번째 시도 성공
        ]

        result = await scraper.fetch_post_stats_limited(
            "post-123", "token-1", "token-2"
        )

        assert result is not None
        assert result["data"]["getStats"]["total"] == 100
        assert mock_fetch.call_count == 2

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
        assert mock_fetch.call_count == 3  # 최대 3번 재시도

    @patch("scraping.main.fetch_velog_user_chk")
    @patch("scraping.main.fetch_all_velog_posts")
    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_process_user_success(
        self, mock_aes, mock_fetch_posts, mock_fetch_user_chk, scraper, user
    ):
        """유저 데이터 전체 처리 성공 테스트"""
        # AES 암호화 모킹
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = (
            lambda token: f"decrypted-{token}"
        )
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

        # 사용자 데이터 및 게시물 모킹
        mock_fetch_user_chk.return_value = (
            {
                "access_token": "new-token",
                "refresh_token": "new-refresh-token",
            },
            {"data": {"currentUser": {"username": "testuser"}}},
        )

        post_uuid = str(uuid.uuid4())
        mock_fetch_posts.return_value = [
            {
                "id": post_uuid,
                "title": "Test Post",
                "url_slug": "test-post",
                "released_at": get_local_now(),
                "likes": 15,
            }
        ]

        # 내부 메서드 모킹
        with (
            patch.object(
                scraper, "update_old_tokens", new_callable=AsyncMock
            ) as mock_update_tokens,
            patch.object(
                scraper, "bulk_upsert_posts", new_callable=AsyncMock
            ) as mock_bulk_upsert,
            patch.object(
                scraper, "sync_post_active_status", new_callable=AsyncMock
            ) as mock_sync_status,
            patch.object(
                scraper, "fetch_post_stats_limited", new_callable=AsyncMock
            ) as mock_fetch_stats,
            patch.object(
                scraper, "update_daily_statistics", new_callable=AsyncMock
            ) as mock_update_stats,
        ):
            # 통계 데이터 모킹
            mock_fetch_stats.return_value = {
                "data": {"getStats": {"total": 150}}
            }

            # 테스트 실행
            await scraper.process_user(user, AsyncMock())

        # 메서드 호출 확인
        mock_update_tokens.assert_called_once()
        mock_bulk_upsert.assert_called_once()
        mock_sync_status.assert_called_once()
        mock_fetch_stats.assert_called_once()
        mock_update_stats.assert_called_once()

    @patch("scraping.main.logger")
    @pytest.mark.asyncio
    async def test_run_method(self, mock_logger, scraper):
        """run 메서드 테스트"""
        # 테스트용 사용자 객체 생성
        test_user = AsyncMock()

        # 비동기 이터레이터를 반환하는 모킹 함수 생성
        async def async_mock_filter(*args, **kwargs):
            for user in [test_user]:
                yield user

        # User.objects.filter 모킹
        with patch("users.models.User.objects.filter") as mock_filter:
            # 비동기 이터레이터를 반환하도록 설정
            mock_filter.return_value = async_mock_filter()

            # aiohttp.ClientSession 모킹
            with patch("aiohttp.ClientSession") as mock_session:
                mock_session_instance = MagicMock()
                mock_session.return_value.__aenter__.return_value = (
                    mock_session_instance
                )

                # process_user 메서드 모킹
                with patch.object(
                    scraper, "process_user", new_callable=AsyncMock
                ) as mock_process:
                    # 실행
                    await scraper.run()

        # 로그 및 메서드 호출 확인
        assert mock_logger.info.call_count >= 2  # 시작과 종료 로그
        mock_process.assert_called_once_with(test_user, mock_session_instance)

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_scraper_target_user_run(self):
        """ScraperTargetUser 클래스의 run 메서드 테스트"""
        from scraping.main import ScraperTargetUser

        # 테스트 사용자 생성
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

        # ScraperTargetUser 인스턴스 생성
        target_scraper = ScraperTargetUser(
            user_pk_list=[test_user.id], max_connections=10
        )

        # process_user 메서드 모킹
        with patch.object(
            target_scraper, "process_user", new_callable=AsyncMock
        ) as mock_process:
            # aiohttp.ClientSession 모킹
            with patch("aiohttp.ClientSession") as mock_session:
                mock_session_instance = MagicMock()
                mock_session.return_value.__aenter__.return_value = (
                    mock_session_instance
                )

                # 실행
                await target_scraper.run()

        # process_user 호출 확인
        mock_process.assert_called_once()
