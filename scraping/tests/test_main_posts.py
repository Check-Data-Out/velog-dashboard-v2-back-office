import uuid
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async

from posts.models import Post
from users.models import User
from utils.utils import get_local_now


class TestScraperPosts:
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

        # sync_to_async가 예외를 발생시키는 AsyncMock을 반환하도록 패치
        with patch("scraping.main.sync_to_async") as mock_sync_to_async:
            mock_sync_to_async.return_value = AsyncMock(
                side_effect=Exception("DB 에러")
            )
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
    async def test_sync_post_active_status(self, scraper):
        """sync_post_active_status 메서드 테스트"""
        # 테스트 사용자 생성
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

        # 다양한 게시물 생성 - 활성 및 비활성
        post_uuid1 = str(uuid.uuid4())
        post_uuid2 = str(uuid.uuid4())
        post_uuid3 = str(uuid.uuid4())
        post_uuid4 = str(uuid.uuid4())

        # 활성 게시물 2개
        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid1,
            title="Active Post 1",
            user=test_user,
            slug="active-post-1",
            released_at=get_local_now(),
            is_active=True,
        )

        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid2,
            title="Active Post 2",
            user=test_user,
            slug="active-post-2",
            released_at=get_local_now(),
            is_active=True,
        )

        # 비활성 게시물 2개
        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid3,
            title="Inactive Post 1",
            user=test_user,
            slug="inactive-post-1",
            released_at=get_local_now(),
            is_active=False,
        )

        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid4,
            title="Inactive Post 2",
            user=test_user,
            slug="inactive-post-2",
            released_at=get_local_now(),
            is_active=False,
        )

        # 현재 API에서 가져온 게시물 ID 집합 (post1과 post3만 포함)
        current_post_ids = {post_uuid1, post_uuid3}

        # sync_post_active_status 메서드 호출
        await scraper.sync_post_active_status(test_user, current_post_ids)

        # 결과 확인: post1 = 활성 유지, post2 = 비활성으로 변경, post3 = 활성화로 변경, post4 = 비활성 유지
        post1 = await sync_to_async(Post.objects.get)(post_uuid=post_uuid1)
        assert post1.is_active is True, "post1 should remain active"

        post2 = await sync_to_async(Post.objects.get)(post_uuid=post_uuid2)
        assert post2.is_active is False, "post2 should be deactivated"

        post3 = await sync_to_async(Post.objects.get)(post_uuid=post_uuid3)
        assert post3.is_active is True, "post3 should be reactivated"

        post4 = await sync_to_async(Post.objects.get)(post_uuid=post_uuid4)
        assert post4.is_active is False, "post4 should remain inactive"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_sync_post_active_status_safety_threshold(self, scraper):
        """sync_post_active_status의 안전 임계값 테스트"""
        # 테스트 사용자 생성
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

        # 10개의 활성 게시물 생성
        post_uuids = [str(uuid.uuid4()) for _ in range(10)]

        for i, post_uuid in enumerate(post_uuids):
            await sync_to_async(Post.objects.create)(
                post_uuid=post_uuid,
                title=f"Active Post {i}",
                user=test_user,
                slug=f"active-post-{i}",
                released_at=get_local_now(),
                is_active=True,
            )

        # 현재 API에서 가져온 게시물 ID 집합 (10개 중 2개만 포함 = 80% 비활성화 예정)
        # 이는 scraper.py의 안전 임계값(50%)을 초과
        current_post_ids = {post_uuids[0], post_uuids[1]}

        # sync_post_active_status 메서드 호출
        await scraper.sync_post_active_status(test_user, current_post_ids)

        # 모든 게시물이 여전히 활성 상태여야 함 (안전 임계값으로 인해 작업이 수행되지 않음)
        for post_uuid in post_uuids:
            post = await sync_to_async(Post.objects.get)(post_uuid=post_uuid)
            assert (
                post.is_active is True
            ), f"Post {post_uuid} should remain active due to safety threshold"
