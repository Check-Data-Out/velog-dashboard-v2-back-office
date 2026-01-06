from collections.abc import Generator
from typing import Any

import pytest

from modules.redis.client import reset_redis_client


@pytest.fixture(autouse=True)
def reset_singleton() -> Generator[None, None, None]:
    """각 테스트 후 싱글톤 인스턴스 리셋."""
    yield
    reset_redis_client()


@pytest.fixture()
def sample_message() -> dict[str, Any]:
    """Sample stats refresh message."""
    return {
        "userId": 123,
        "requestedAt": "2025-12-12T10:30:00Z",
        "retryCount": 0,
    }
