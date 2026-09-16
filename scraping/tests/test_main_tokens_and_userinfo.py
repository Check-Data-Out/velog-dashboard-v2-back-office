import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from scraping.main import ScraperTargetUser
from users.models import User

MISSING_VIEWS = object()


async def run_process_user(scraper, user, mock_user_data, posts):
    """process_user 를 실행하고 update_daily_statistics mock 을 반환."""
    with (
        patch("scraping.main.AESEncryption") as mock_aes,
        patch("scraping.main.fetch_velog_user_chk") as mock_chk,
        patch("scraping.main.fetch_all_velog_posts") as mock_posts,
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch.object(
            scraper,
            "update_old_tokens",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(
            scraper,
            "update_old_user_info",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(scraper, "bulk_upsert_posts", new_callable=AsyncMock),
        patch.object(
            scraper, "sync_post_active_status", new_callable=AsyncMock
        ),
        patch.object(
            scraper, "update_daily_statistics", new_callable=AsyncMock
        ) as mock_update_stats,
    ):
        encryption = mock_aes.return_value
        encryption.decrypt.side_effect = lambda token: f"decrypted-{token}"
        encryption.encrypt.side_effect = lambda token: f"encrypted-{token}"
        mock_chk.return_value = (
            {
                "access_token": "new-token",
                "refresh_token": "new-refresh-token",
            },
            mock_user_data,
        )
        mock_posts.return_value = posts

        await scraper.process_user(user, AsyncMock())

    return mock_update_stats


class TestScraperTokenAndUserInfoAndProcessing:
    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_tokens_success(
        self, mock_aes, scraper, user, mock_new_tokens
    ) -> None:
        """토큰 업데이트 성공 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = (
            lambda token: f"decrypted-{token}"
        )
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_tokens(
                user, mock_encryption, mock_new_tokens
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

        # 동일한 토큰으로 설정
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

        # 이미 복호화된 형태의 토큰 (변경 없음)
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
        self, mock_aes, scraper, user, mock_new_tokens
    ):
        """복호화가 제대로 되지 않았을 경우 업데이트 실패 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = lambda token: None
        mock_encryption.encrypt.side_effect = (
            lambda token: f"encrypted-{token}"
        )

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_tokens(
                user, mock_encryption, mock_new_tokens
            )

        assert result is False
        mock_asave.assert_not_called()

    @pytest.mark.parametrize(
        "views, expected",
        [
            (150, [150]),
            (None, []),
            (0, [0]),
            (MISSING_VIEWS, []),
        ],
        ids=["정상값", "None은건너뜀", "0도저장", "키부재도건너뜀"],
    )
    @pytest.mark.asyncio
    async def test_process_user_writes_views_as_stats(
        self, views, expected, scraper, user, mock_user_data, mock_posts_data
    ):
        """posts 응답의 views 가 그대로 통계가 되는지.

        views 는 누적 스냅샷이라 값이 없을 때 0 을 쓰면 급락으로 오염된다.
        반대로 0 은 신규 글의 정상값이므로 건너뛰면 안 된다.
        """
        post = dict(mock_posts_data[0])
        if views is MISSING_VIEWS:
            post.pop("views")
        else:
            post["views"] = views

        mock_update_stats = await run_process_user(
            scraper, user, mock_user_data, [post]
        )

        written = [call.args[1] for call in mock_update_stats.call_args_list]
        assert written == expected

    @patch("scraping.main.logger")
    @pytest.mark.asyncio
    async def test_process_users_isolates_failing_user(
        self, mock_logger, scraper, user
    ):
        """한 유저가 터져도 나머지 유저는 계속 처리하는지.

        격리가 없으면 예외가 프로세스를 죽여 그 그룹의 남은 유저가
        통째로 누락된다.
        """
        other = MagicMock(spec=User)
        other.velog_uuid = "other-uuid"

        with patch.object(
            scraper,
            "process_user",
            new_callable=AsyncMock,
            side_effect=[ValueError("boom"), None],
        ) as mock_process:
            await scraper.process_users([user, other], AsyncMock())

        assert mock_process.call_count == 2
        assert mock_logger.error.called

    @patch("scraping.main.logger")
    @pytest.mark.asyncio
    async def test_process_user_reports_total_failure(
        self, mock_logger, scraper, user, mock_user_data, mock_posts_data
    ):
        """전량 실패를 성공으로 보고하지 않는지.

        이번 장애에서 통계가 0건인데 성공 로그만 남아 2일간 무감지였다.
        """
        posts = [{**p, "views": None} for p in mock_posts_data]

        await run_process_user(scraper, user, mock_user_data, posts)

        assert not any(
            "Succeeded to update stats" in str(c)
            for c in mock_logger.info.call_args_list
        )
        assert mock_logger.error.called

    @patch("scraping.main.logger")
    @pytest.mark.asyncio
    async def test_process_user_reports_partial_failure(
        self, mock_logger, scraper, user, mock_user_data, mock_posts_data
    ):
        """일부만 실패하면 건수와 함께 경고하는지"""
        posts = [
            dict(mock_posts_data[0]),
            {**mock_posts_data[1], "views": None},
        ]

        await run_process_user(scraper, user, mock_user_data, posts)

        assert any(
            "succeeded=1" in str(c) and "failed=1" in str(c)
            for c in mock_logger.warning.call_args_list
        )

    @patch("scraping.main.logger")
    @pytest.mark.asyncio
    async def test_process_user_reports_success(
        self, mock_logger, scraper, user, mock_user_data, mock_posts_data
    ):
        """전량 성공이면 기존 성공 로그가 그대로 남는지.

        실패 방향만 검증하면 성공 시에도 경고만 찍는 반대 회귀를 놓친다.
        """
        await run_process_user(scraper, user, mock_user_data, mock_posts_data)

        assert any(
            "Succeeded to update stats" in str(c)
            for c in mock_logger.info.call_args_list
        )

    @pytest.mark.asyncio
    async def test_process_user_writes_stats_for_every_post(
        self, scraper, user, mock_user_data, mock_posts_data
    ):
        """여러 포스트가 각자의 views 로 순서대로 저장되는지"""
        mock_update_stats = await run_process_user(
            scraper, user, mock_user_data, mock_posts_data
        )

        written = [call.args[1] for call in mock_update_stats.call_args_list]
        assert written == [150, 320]

    @patch("scraping.main.fetch_velog_user_chk")
    @patch("scraping.main.fetch_all_velog_posts")
    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_process_user_success(
        self,
        mock_aes,
        mock_fetch_posts,
        mock_fetch_user_chk,
        scraper,
        user,
        mock_user_data,
        mock_posts_data,
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

        # 새 토큰과 사용자 데이터 모킹
        mock_fetch_user_chk.return_value = (
            {
                "access_token": "new-token",
                "refresh_token": "new-refresh-token",
            },
            mock_user_data,
        )
        mock_fetch_posts.return_value = mock_posts_data

        # 내부 메서드 모킹 - 성공 케이스로 설정
        with (
            patch.object(
                scraper,
                "update_old_tokens",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_update_tokens,
            patch.object(
                scraper,
                "update_old_user_info",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_update_user_info,
            patch.object(
                scraper, "bulk_upsert_posts", new_callable=AsyncMock
            ) as mock_bulk_upsert,
            patch.object(
                scraper, "sync_post_active_status", new_callable=AsyncMock
            ) as mock_sync_status,
            patch.object(
                scraper, "update_daily_statistics", new_callable=AsyncMock
            ),
        ):
            # 테스트 실행
            await scraper.process_user(user, AsyncMock())

        # 메서드 호출 확인
        mock_update_tokens.assert_called_once()
        mock_update_user_info.assert_called_once()

        # update_old_user_info가 currentUser 객체로 호출되었는지 확인
        args, kwargs = mock_update_user_info.call_args
        assert args[1] == mock_user_data["data"]["currentUser"]

        mock_bulk_upsert.assert_called_once()
        mock_sync_status.assert_called_once()

    @patch("scraping.main.fetch_velog_user_chk")
    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_process_user_token_update_failure(
        self, mock_aes, mock_fetch_user_chk, scraper, user, mock_user_data
    ):
        """토큰 업데이트 실패 시 예외 발생 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = (
            lambda token: f"decrypted-{token}"
        )

        mock_fetch_user_chk.return_value = (
            {
                "access_token": "new-token",
                "refresh_token": "new-refresh-token",
            },
            mock_user_data,
        )

        # update_old_tokens가 False 반환하도록 모킹
        with patch.object(
            scraper,
            "update_old_tokens",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(Exception, match="Failed to update tokens"):
                await scraper.process_user(user, AsyncMock())

    @patch("scraping.main.fetch_velog_user_chk")
    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_process_user_user_info_update_failure(
        self, mock_aes, mock_fetch_user_chk, scraper, user, mock_user_data
    ):
        """사용자 정보 업데이트 실패 시 예외 발생 테스트"""
        mock_encryption = mock_aes.return_value
        mock_encryption.decrypt.side_effect = (
            lambda token: f"decrypted-{token}"
        )

        mock_fetch_user_chk.return_value = (
            {
                "access_token": "new-token",
                "refresh_token": "new-refresh-token",
            },
            mock_user_data,
        )

        with (
            patch.object(
                scraper,
                "update_old_tokens",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(
                scraper,
                "update_old_user_info",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(Exception, match="Failed to update user_info"):
                await scraper.process_user(user, AsyncMock())

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
        # 테스트 사용자 생성
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            username="testuser",
            thumbnail="https://example.com/thumb.jpg",
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

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_user_info_success(self, mock_aes, scraper, user):
        """사용자 정보 업데이트 성공 테스트"""
        user_data = {
            "email": "new@example.com",
            "username": "newuser",
            "profile": {"thumbnail": "https://newexample.com/thumb.jpg"},
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_user_info(user, user_data)

        assert result is True
        mock_asave.assert_called_once()
        assert user.email == "new@example.com"
        assert user.username == "newuser"
        assert user.thumbnail == "https://newexample.com/thumb.jpg"

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_user_info_no_changes(
        self, mock_aes, scraper, user
    ):
        """변경사항 없을 때 테스트"""
        # 기존 값과 동일하게 설정
        user.email = "same@example.com"
        user.username = "sameuser"
        user.thumbnail = "https://same.com/thumb.jpg"

        # 동일한 값으로 설정하여 변경사항 없도록 함
        user_data = {
            "email": "same@example.com",
            "username": "sameuser",
            "profile": {"thumbnail": "https://same.com/thumb.jpg"},
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_user_info(user, user_data)

        assert result is True
        mock_asave.assert_not_called()  # 변경사항 없으므로 asave 호출 안됨

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_user_info_partial_update(
        self, mock_aes, scraper, user
    ):
        """일부 필드만 업데이트되는 경우 테스트"""
        user.email = "old@example.com"
        user.username = "olduser"
        user.thumbnail = None  # 기존에 썸네일이 없는 경우

        user_data = {
            "email": "old@example.com",  # 동일한 이메일
            "username": "newuser",  # 새로운 사용자명
            "profile": {
                "thumbnail": "https://new.com/thumb.jpg"  # 새로운 썸네일
            },
        }

        with patch.object(user, "asave", new_callable=AsyncMock) as mock_asave:
            result = await scraper.update_old_user_info(user, user_data)

        assert result is True
        mock_asave.assert_called_once()
        # 변경된 필드만 확인
        assert user.username == "newuser"
        assert user.thumbnail == "https://new.com/thumb.jpg"
        # 기존 값 유지 확인
        assert user.email == "old@example.com"

    @patch("scraping.main.AESEncryption")
    @pytest.mark.asyncio
    async def test_update_old_user_info_exception_handling(
        self, mock_aes, scraper, user
    ):
        """사용자 정보 업데이트 중 예외 발생 테스트"""
        user_data = {
            "email": "new@example.com",
            "username": "newuser",
            "profile": {"thumbnail": "https://new.com/thumb.jpg"},
        }

        # asave에서 예외 발생하도록 모킹
        with patch.object(
            user,
            "asave",
            new_callable=AsyncMock,
            side_effect=Exception("DB Error"),
        ):
            result = await scraper.update_old_user_info(user, user_data)

        assert result is False
