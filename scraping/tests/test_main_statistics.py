import uuid

import pytest
from asgiref.sync import sync_to_async

from posts.models import Post, PostDailyStatistics
from users.models import User
from utils.utils import get_local_now


class TestScraperStatistics:
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

        # update_daily_statistics 호출
        result = await scraper.update_daily_statistics(post_data, 150)

        # 결과 확인
        today = get_local_now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        stats = await sync_to_async(PostDailyStatistics.objects.get)(
            post__post_uuid=post_uuid, date=today
        )

        assert result is True
        assert stats.daily_view_count == 150
        assert stats.daily_like_count == 25

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_daily_statistics_returns_false_for_unknown_post(
        self, scraper
    ):
        """DB 에 없는 post 면 False 를 반환하는지.

        호출부가 이 반환값으로 성공 건수를 세므로, True 로 새면 0건
        기록된 유저가 전량 성공으로 로깅된다.
        """
        result = await scraper.update_daily_statistics(
            {"id": str(uuid.uuid4()), "likes": 1}, 100
        )

        assert result is False
