from typing import Any

import pytest


@pytest.fixture()
def sample_message() -> dict[str, Any]:
    """Sample stats refresh message."""
    return {
        "userId": 123,
        "requestedAt": "2025-12-12T10:30:00Z",
        "retryCount": 0,
    }
