import pytest
from unittest.mock import AsyncMock, MagicMock

from scraping.main import Scraper
from users.models import User
from posts.models import Post


@pytest.mark.asyncio
async def test_update_old_tokens(db, mocker):
    """토큰 만료로 인한 토큰 업데이트 테스트"""
    mock_logger = mocker.patch("scraping.main.logging.getLogger")

    user = User(
        velog_uuid="test-uuid",
        access_token="old_access",
        refresh_token="old_refresh",
    )

    aes_encryption = MagicMock()
    aes_encryption.encrypt.side_effect = lambda x: f"encrypted_{x}"

    user_cookies = {
        "access_token": "new_access", 
        "refresh_token": "new_refresh"
    }

    main = Scraper(group_range=range(1, 2))
    main.logger = mock_logger

    await main.update_old_tokens(user, aes_encryption, user_cookies, "old_access", "old_refresh")

    assert user.access_token == "encrypted_new_access"
    assert user.refresh_token == "encrypted_new_refresh"


@pytest.mark.asyncio
async def test_bulk_create_posts(mocker):
    """Post 객체 대량 생성 테스트"""
    mock_logger = mocker.patch("scraping.main.logging.getLogger")

    user = User(velog_uuid="test-uuid")
    fetched_posts = [
        {"id": "id1", "title": "title1", "url_slug": "url_slug1", "released_at": "2025-01-01"},
        {"id": "id2", "title": "title2", "url_slug": "url_slug2", "released_at": "2025-01-01"},
    ]

    mock_abulk_create = mocker.patch.object(Post.objects, "abulk_create", new_callable=AsyncMock)

    main = Scraper(group_range=range(1, 2))
    main.logger = mock_logger

    result = await main.bulk_create_posts(user, fetched_posts)

    mock_abulk_create.assert_called_once()
    assert result is True

from posts.models import PostDailyStatistics


@pytest.mark.asyncio
async def test_update_daily_statistics(mocker):
    """PostDailyStatistics를 업데이트 또는 생성하는 기능 테스트"""

    mock_logger = mocker.patch("scraping.main.logging.getLogger")
    
    post = {"id": "post1", "likes": 5}
    stats = {
        "data": {
            "getStats": {
                "total": 100
            }
        }
    }

    post_obj = MagicMock(spec=Post)
    mocker.patch("scraping.main.sync_to_async", return_value=AsyncMock(return_value=post_obj))

    daily_stats_mock = AsyncMock(spec=PostDailyStatistics)

    daily_stats_mock.daily_view_count = 50
    daily_stats_mock.daily_like_count = 3

    def setattr_mock(self, name, value):
        object.__setattr__(self, name, value)

    daily_stats_mock.__setattr__ = setattr_mock.__get__(daily_stats_mock)

    mock_get_or_create = mocker.patch(
        "posts.models.PostDailyStatistics.objects.aget_or_create",
        return_value=(daily_stats_mock, False),
    )

    scraper = Scraper(group_range=range(1, 2))
    scraper.logger = mock_logger

    await scraper.update_daily_statistics(post, stats)

    mock_get_or_create.assert_called_once_with(
        post=post_obj,
        date=scraper.get_local_now().date(),
        defaults={"daily_view_count": 100, "daily_like_count": 5},
    )

    assert daily_stats_mock.daily_view_count == 100, "daily_view_count 업데이트 실패"
    assert daily_stats_mock.daily_like_count == 5, "daily_like_count 업데이트 실패"

    daily_stats_mock.asave.assert_awaited_once()
