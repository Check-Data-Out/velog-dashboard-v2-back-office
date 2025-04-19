import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.db import transaction

from posts.models import Post, PostDailyStatistics
from scraping.main import Scraper
from users.models import User
from utils.utils import get_local_now


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

    @pytest.mark.asyncio
    async def test_bulk_upsert_posts_success(self, scraper, user):
        """Post 객체 배치 분할 삽입 또는 업데이트 성공 테스트"""
        posts_data = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Title {i}",
                "url_slug": f"slug-{i}",
                "released_at": get_local_now(),
            }
            for i in range(50)
        ]

        # _upsert_batch 메서드만 모킹
        with patch.object(
            scraper, "_upsert_batch", new_callable=AsyncMock
        ) as mock_upsert:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await scraper.bulk_upsert_posts(
                    user, posts_data, batch_size=10
                )

        assert result is True
        # 50개 / 10개 배치 = 5번 호출
        assert mock_upsert.call_count == 5

    @pytest.mark.asyncio
    async def test_bulk_upsert_posts_failure(self, scraper, user):
        """Post 객체 배치 분할 삽입 또는 업데이트 실패 테스트"""
        posts_data = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Title {i}",
                "url_slug": f"slug-{i}",
                "released_at": get_local_now(),
            }
            for i in range(10)
        ]

        # 실제 예외를 발생시키는 비동기 함수 생성
        async def mock_async_error(*args, **kwargs):
            raise Exception("DB 에러")

        # sync_to_async가 적절한 비동기 함수를 반환하도록 패치
        with patch("scraping.main.sync_to_async") as mock_sync_to_async:
            mock_sync_to_async.return_value = mock_async_error
            result = await scraper.bulk_upsert_posts(
                user, posts_data, batch_size=5
            )

        assert result is False
        mock_sync_to_async.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_upsert_batch_creates_and_updates(self, scraper):
        """
        _upsert_batch 메서드가 기존 게시물을 업데이트하고, 신규 게시물을 생성하는지 검증합니다.
        """
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

        # 기존 게시물 생성 (sync_to_async로 감싸줌)
        existing_post_uuid = str(uuid.uuid4())
        original_title = "Original Title"
        original_slug = "original-slug"
        original_time = get_local_now()
        await sync_to_async(Post.objects.create)(
            post_uuid=existing_post_uuid,
            title=original_title,
            user=test_user,
            slug=original_slug,
            released_at=original_time,
        )

        # 배치 데이터 준비: 기존 게시물 업데이트용과 신규 게시물 생성용 데이터 포함
        updated_title = "Updated Title"
        updated_slug = "updated-slug"
        updated_time = get_local_now()

        new_post_uuid = str(uuid.uuid4())
        new_title = "New Title"
        new_slug = "new-slug"
        new_time = get_local_now()

        batch_posts = [
            {
                "id": existing_post_uuid,
                "title": updated_title,
                "url_slug": updated_slug,
                "released_at": updated_time,
            },
            {
                "id": new_post_uuid,
                "title": new_title,
                "url_slug": new_slug,
                "released_at": new_time,
            },
        ]

        # _upsert_batch 호출
        await scraper._upsert_batch(test_user, batch_posts)

        # 기존 게시물 업데이트 확인 (sync_to_async 사용)
        updated_post = await sync_to_async(Post.objects.get)(
            post_uuid=existing_post_uuid
        )
        assert updated_post.title == updated_title
        assert updated_post.slug == updated_slug
        assert updated_post.released_at == updated_time

        # 신규 게시물 생성 확인 (sync_to_async 사용)
        new_post = await sync_to_async(Post.objects.get)(
            post_uuid=new_post_uuid
        )
        assert new_post.title == new_title
        assert new_post.slug == new_slug
        assert new_post.released_at == new_time

        # user 관계 필드를 직접 비교하지 말고 ID로 비교
        new_post_user_id = await sync_to_async(lambda: new_post.user_id)()
        assert new_post_user_id == test_user.id

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_upsert_batch_deactivates_old_posts(self, scraper):
        """
        _upsert_batch 메서드가 더 이상 API에서 반환되지 않는 게시물을 비활성화하는지 검증합니다.
        """
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

        # 기존 활성화 상태의 게시물 3개 생성
        post_uuid1 = str(uuid.uuid4())
        post_uuid2 = str(uuid.uuid4())
        post_uuid3 = str(uuid.uuid4())

        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid1,
            title="Post 1",
            user=test_user,
            slug="post-1",
            released_at=get_local_now(),
            is_active=True,
        )

        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid2,
            title="Post 2",
            user=test_user,
            slug="post-2",
            released_at=get_local_now(),
            is_active=True,
        )

        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid3,
            title="Post 3",
            user=test_user,
            slug="post-3",
            released_at=get_local_now(),
            is_active=True,
        )

        # 새로운 배치 데이터에는 post_uuid1만 포함 (나머지는 비활성화되어야 함)
        batch_posts = [
            {
                "id": post_uuid1,
                "title": "Updated Post 1",
                "url_slug": "updated-post-1",
                "released_at": get_local_now(),
            }
        ]

        # _upsert_batch 호출
        await scraper._upsert_batch(test_user, batch_posts)

        # 게시물 상태 확인
        # post_uuid1은 여전히 활성 상태여야 함
        post1 = await sync_to_async(Post.objects.get)(post_uuid=post_uuid1)
        assert post1.is_active is True
        assert post1.title == "Updated Post 1"

        # post_uuid2와 post_uuid3는 비활성 상태로 변경되어야 함
        post2 = await sync_to_async(Post.objects.get)(post_uuid=post_uuid2)
        assert post2.is_active is False

        post3 = await sync_to_async(Post.objects.get)(post_uuid=post_uuid3)
        assert post3.is_active is False

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_upsert_batch_reactivates_inactive_posts(self, scraper):
        """
        _upsert_batch 메서드가 비활성화된 게시물이 다시 API 결과에 포함될 경우 재활성화하는지 검증합니다.
        """
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

        # 비활성화된 게시물 생성
        inactive_post_uuid = str(uuid.uuid4())
        await sync_to_async(Post.objects.create)(
            post_uuid=inactive_post_uuid,
            title="Inactive Post",
            user=test_user,
            slug="inactive-post",
            released_at=get_local_now(),
            is_active=False,
        )

        # 배치 데이터에 비활성화된 게시물 포함
        batch_posts = [
            {
                "id": inactive_post_uuid,
                "title": "Reactivated Post",
                "url_slug": "reactivated-post",
                "released_at": get_local_now(),
            }
        ]

        # _upsert_batch 호출
        await scraper._upsert_batch(test_user, batch_posts)

        # 게시물 상태 확인 - 재활성화되어야 함
        post = await sync_to_async(Post.objects.get)(
            post_uuid=inactive_post_uuid
        )
        assert post.is_active is True
        assert post.title == "Reactivated Post"
        assert post.slug == "reactivated-post"

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
    @pytest.mark.asyncio
    async def test_process_user_failure_rollback(
        self, mock_atomic, scraper, user
    ):
        """유저 데이터 처리 실패 시 롤백 확인 테스트"""
        mock_session = AsyncMock()
        mock_atomic.side_effect = transaction.atomic

        with patch(
            "scraping.main.fetch_velog_user_chk",
            side_effect=Exception("Failed to fetch user data"),
        ):
            with pytest.raises(Exception):
                await scraper.process_user(user, mock_session)

        # 동기 쿼리를 비동기로 변환
        count = await sync_to_async(Post.objects.filter(user=user).count)()
        assert count == 0

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_process_user_partial_failure_rollback(self, scraper, user):
        """통계 업데이트 중 실패 시 롤백 확인 테스트"""
        mock_session = AsyncMock()
        post_uuid = uuid.uuid4()

        # 테스트용 게시물 직접 생성
        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid,
            user=user,
            title="Test Post",
            slug="test-slug",
            released_at=get_local_now(),
        )

        # fetch_post_stats_limited 메서드에서 예외 발생시키기
        with patch.object(
            scraper,
            "fetch_post_stats_limited",
            side_effect=Exception("Failed to fetch stats"),
        ):
            # bulk_upsert_posts 성공하도록 모킹
            with patch.object(
                scraper, "bulk_upsert_posts", new_callable=AsyncMock
            ) as mock_bulk_upsert:
                mock_bulk_upsert.return_value = True

                # 다른 필요한 API 호출도 모킹
                with (
                    patch(
                        "scraping.apis.fetch_velog_user_chk",
                        new_callable=AsyncMock,
                    ) as mock_user_chk,
                    patch(
                        "scraping.apis.fetch_all_velog_posts",
                        new_callable=AsyncMock,
                    ) as mock_posts,
                ):
                    # 사용자 정보 모킹
                    mock_user_chk.return_value = (
                        {},
                        {"data": {"currentUser": {"username": "testuser"}}},
                    )

                    # 게시물 정보 모킹
                    mock_posts.return_value = [
                        {
                            "id": post_uuid,
                            "title": "Test Post",
                            "url_slug": "test-slug",
                            "released_at": get_local_now(),
                        }
                    ]

                    # 예외를 처리하지만 게시물은 여전히 존재해야 함
                    try:
                        await scraper.process_user(user, mock_session)
                    except Exception:
                        pass

        # 게시물이 존재하는지 확인 (sync_to_async로 래핑)
        exists_func = sync_to_async(
            lambda: Post.objects.filter(user=user).exists()
        )
        exists = await exists_func()
        assert exists

        # 통계 정보가 없는지 확인
        has_stats_func = sync_to_async(
            lambda: PostDailyStatistics.objects.filter(
                post__user=user
            ).exists()
        )
        has_stats = await has_stats_func()
        assert not has_stats
