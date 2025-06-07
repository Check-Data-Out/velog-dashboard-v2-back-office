import uuid

import pytest

from scraping.main import Scraper
from users.models import User


@pytest.fixture
def scraper():
    """Scraper 인스턴스 생성"""
    return Scraper(group_range=range(1, 10), max_connections=10)


@pytest.fixture
def user(db):
    """테스트용 User 객체 생성"""
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="encrypted-access-token",
        refresh_token="encrypted-refresh-token",
        group_id=1,
        email="test@example.com",
        username="nuung",
        thumbnail="https://nuung.com",
        is_active=True,
    )


@pytest.fixture
def mock_user_data():
    """테스트용 user_data 구조"""
    return {
        "data": {
            "currentUser": {
                "id": "user-123",
                "email": "test@example.com",
                "username": "testuser",
                "profile": {"thumbnail": "https://example.com/thumbnail.jpg"},
            }
        }
    }


@pytest.fixture
def mock_new_tokens():
    """테스트용 새 토큰"""
    return {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
    }


@pytest.fixture
def mock_posts_data():
    """테스트용 게시물 데이터"""
    return [
        {
            "id": str(uuid.uuid4()),
            "title": "Test Post 1",
            "url_slug": "test-post-1",
            "released_at": "2024-01-01T00:00:00Z",
            "likes": 15,
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Test Post 2",
            "url_slug": "test-post-2",
            "released_at": "2024-01-02T00:00:00Z",
            "likes": 25,
        },
    ]


@pytest.fixture
def mock_stats_data():
    """테스트용 통계 데이터"""
    return {"data": {"getStats": {"total": 150}}}
