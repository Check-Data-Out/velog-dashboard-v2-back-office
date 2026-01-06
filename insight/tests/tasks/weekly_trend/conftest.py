import pytest


@pytest.fixture
def analyzer():
    from insight.tasks.weekly_trend_analysis import WeeklyTrendAnalyzer

    return WeeklyTrendAnalyzer(trending_limit=1)
