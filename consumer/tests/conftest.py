"""Pytest fixtures for consumer tests."""

import uuid
from unittest.mock import MagicMock, Mock

import pytest
import redis

from users.models import User


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock_client = MagicMock(spec=redis.Redis)
    mock_client.ping.return_value = True
    mock_client.brpop.return_value = None
    mock_client.lpush.return_value = 1
    mock_client.lrem.return_value = 1
    mock_client.llen.return_value = 0
    mock_client.close.return_value = None
    return mock_client


@pytest.fixture
def sample_message():
    """Sample stats refresh message."""
    return {
        "userId": 123,
        "requestedAt": "2025-12-12T10:30:00Z",
        "retryCount": 0,
    }


@pytest.fixture
def invalid_message():
    """Invalid message without userId."""
    return {
        "requestedAt": "2025-12-12T10:30:00Z",
    }


@pytest.fixture
def test_user(db):
    """Create a test user."""
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        group_id=1,
        email="consumer-test@example.com",
        username="consumer_test_user",
        is_active=True,
    )


@pytest.fixture
def mock_scraper():
    """Mock ScraperTargetUser."""
    mock = Mock()
    mock.run = Mock()
    return mock
