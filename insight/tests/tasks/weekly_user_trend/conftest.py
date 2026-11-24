from datetime import date

import pytest

from insight.models import WeeklyTrend


@pytest.fixture
def user_trend_module(mock_setup_django):
    # 모듈 맨 위의 import setup_django 를 흉내 낸 뒤에만 불러올 수 있다
    from insight.tasks import weekly_user_trend_analysis

    return weekly_user_trend_analysis


@pytest.fixture
def analyzer_user(user_trend_module):
    # 저장하지 않은 공통 분석 행. 단위 테스트는 주차를 mock_context 로 준다
    return user_trend_module.UserWeeklyAnalyzer(
        WeeklyTrend(
            week_start_date=date(2025, 7, 21), week_end_date=date(2025, 7, 27)
        )
    )
