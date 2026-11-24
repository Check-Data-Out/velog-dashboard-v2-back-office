import pytest


@pytest.fixture
def user_trend_module(mock_setup_django):
    # 모듈 맨 위의 import setup_django 를 흉내 낸 뒤에만 불러올 수 있다
    from insight.tasks import weekly_user_trend_analysis

    return weekly_user_trend_analysis


@pytest.fixture
def analyzer_user(user_trend_module):
    return user_trend_module.UserWeeklyAnalyzer()
