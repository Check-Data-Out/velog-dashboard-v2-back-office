import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.admin.sites import AdminSite
from django.http import HttpRequest

from insight.admin import UserWeeklyTrendAdmin, WeeklyTrendAdmin
from insight.models import (
    TrendAnalysis,
    TrendingItem,
    UserWeeklyTrend,
    WeeklyTrend,
    WeeklyTrendInsight,
)
from users.models import User


@pytest.fixture
def user(db):
    """일반 User 객체 생성"""
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        group_id=1,
        email="test@example.com",
        is_active=True,
    )


@pytest.fixture
def admin_site():
    """Django AdminSite 인스턴스"""
    return AdminSite()


@pytest.fixture
def weekly_trend_admin(admin_site):
    return WeeklyTrendAdmin(WeeklyTrend, admin_site)


@pytest.fixture
def user_weekly_trend_admin(admin_site):
    return UserWeeklyTrendAdmin(UserWeeklyTrend, admin_site)


@pytest.fixture
def request_factory():
    """테스트용 요청 객체 생성"""
    request = HttpRequest()
    request._messages = MagicMock()
    return request


@pytest.fixture
def sample_trend_analysis():
    """테스트용 트렌드 분석 데이터"""
    return TrendAnalysis(
        hot_keywords=["Python", "Django", "React"],
        title_trends="기술 관련 블로그가 인기",
        content_trends="튜토리얼 형태의 콘텐츠 증가",
        insights="주로 개발자들이 기술 공유를 위해 작성",
    )


@pytest.fixture
def sample_trending_items():
    """테스트용 트렌딩 항목 데이터"""
    return [
        TrendingItem(
            title="Django와 React로 풀스택 개발하기",
            summary="Django 백엔드와 React 프론트엔드를 연결하는 방법",
            key_points=["Django REST Framework", "React Hooks", "JWT 인증"],
            username="test1",
            thumbnail="https://velog.io/sample1.jpg",
            slug="django-react-fullstack",
        ),
        TrendingItem(
            title="파이썬 성능 최적화 기법",
            summary="파이썬 코드를 더 빠르게 실행하는 방법",
            key_points=["프로파일링", "메모리 관리", "C 확장 모듈"],
            username="test2",
            thumbnail="https://velog.io/sample2.jpg",
            slug="python-performance",
        ),
    ]


@pytest.fixture
def sample_weekly_trend_insight(sample_trend_analysis, sample_trending_items):
    """테스트용 주간 트렌드 인사이트 데이터"""
    return WeeklyTrendInsight(
        trending_summary=sample_trending_items,
        trend_analysis=sample_trend_analysis,
    )


@pytest.fixture
def weekly_trend(
    db, sample_weekly_trend_insight: WeeklyTrendInsight
) -> WeeklyTrend:
    """주간 트렌드 생성"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    return WeeklyTrend.objects.create(
        week_start_date=week_start,
        week_end_date=week_end,
        insight=sample_weekly_trend_insight.to_json_dict(),
    )


@pytest.fixture
def user_weekly_trend(
    db, user, sample_weekly_trend_insight: WeeklyTrendInsight
) -> UserWeeklyTrend:
    """사용자 주간 트렌드 생성"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    insight_dict = sample_weekly_trend_insight.to_json_dict()
    # 사용자 인사이트는 제목을 조금 다르게 설정
    if insight_dict["trending_summary"]:
        insight_dict["trending_summary"][0]["title"] = "Django 모델 최적화하기"
        insight_dict["trending_summary"][0]["summary"] = (
            "Django ORM을 효율적으로 사용하는 방법"
        )

    return UserWeeklyTrend.objects.create(
        user=user,
        week_start_date=week_start,
        week_end_date=week_end,
        insight=insight_dict,
    )


@pytest.fixture
def empty_insight_weekly_trend(db):
    """빈 인사이트를 가진 주간 트렌드"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    return WeeklyTrend.objects.create(
        week_start_date=week_start, week_end_date=week_end, insight={}
    )
