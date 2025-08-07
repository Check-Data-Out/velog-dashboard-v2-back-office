from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

import pytest


@pytest.fixture
def analyzer_user():
    from insight.tasks.weekly_user_trend_analysis import UserWeeklyAnalyzer
    return UserWeeklyAnalyzer()
