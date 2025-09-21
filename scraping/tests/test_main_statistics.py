import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from posts.models import Post, PostDailyStatistics
from users.models import User
from utils.utils import get_local_now


class TestScraperStatistics:
    @pytest.mark.asyncio
    async def test_update_daily_statistics_success(self, scraper):
        """데일리 통계 업데이트 또는 생성 성공 테스트"""
        post_data = {"id": "post-123", "likes": 10}
        stats_data = {"data": {"getStats": {"total": 100}}}

        with patch(
            "scraping.main.sync_to_async", new_callable=MagicMock
        ) as mock_sync_to_async:
            mock_async_func = AsyncMock()
            mock_sync_to_async.return_value = mock_async_func

            await scraper.update_daily_statistics(post_data, stats_data)

            mock_sync_to_async.assert_called()
            mock_async_func.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_daily_statistics_integration(self, scraper):
        """데일리 통계 업데이트 통합 테스트"""
        # 테스트 사용자 및 게시물 생성
        test_user = await sync_to_async(User.objects.create)(
            velog_uuid=uuid.uuid4(),
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="test@example.com",
            is_active=True,
        )

        post_uuid = str(uuid.uuid4())
        await sync_to_async(Post.objects.create)(
            post_uuid=post_uuid,
            title="Test Post",
            user=test_user,
            slug="test-post",
            released_at=get_local_now(),
            is_active=True,
        )

        # 통계 데이터 준비
        post_data = {"id": post_uuid, "likes": 25}
        stats_data = {"data": {"getStats": {"total": 150}}}

        # update_daily_statistics 호출
        await scraper.update_daily_statistics(post_data, stats_data)

        # 결과 확인
        today = get_local_now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        stats = await sync_to_async(PostDailyStatistics.objects.get)(
            post__post_uuid=post_uuid, date=today
        )

        assert stats.daily_view_count == 150
        assert stats.daily_like_count == 25
