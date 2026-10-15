import uuid

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from django.db import connections

from scraping.main import Scraper
from scraping.reporting import reset_report_window
from users.models import User


@pytest.fixture(autouse=True)
def _reset_report_window():
    """보고 헬퍼의 윈도/억제 상태가 테스트 간에 누수되지 않도록.

    윈도 상태는 source=velog-api 호출(scraping/apis.py)만 바꾸고 consumer 는
    source 없이 호출하므로 scraping 테스트 패키지에만 둔다.
    """
    reset_report_window()
    yield
    reset_report_window()


@pytest_asyncio.fixture(autouse=True)
async def _close_sync_to_async_db_connections():
    """sync_to_async 워커 스레드의 DB 연결을 닫는다.

    남아 있으면 세션 종료 시 test DB DROP 이 "being accessed by other users" 로 실패한다.
    """
    yield
    await sync_to_async(connections.close_all)()


@pytest.fixture
def scraper():
    """Scraper 인스턴스 생성"""
    return Scraper(group_range=range(1, 10))


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
            "views": 150,
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Test Post 2",
            "url_slug": "test-post-2",
            "released_at": "2024-01-02T00:00:00Z",
            "likes": 25,
            "views": 320,
        },
    ]
