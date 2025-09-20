import sys
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.http import HttpRequest

from insight.admin import UserWeeklyTrendAdmin, WeeklyTrendAdmin
from insight.models import (
    TrendAnalysis,
    TrendingItem,
    UserWeeklyTrend,
    WeeklyTrend,
    WeeklyTrendInsight,
    WeeklyUserReminder,
    WeeklyUserStats,
    WeeklyUserTrendInsight,
)
from insight.schemas import Newsletter
from modules.mail.schemas import EmailMessage
from users.models import User
from utils.utils import get_previous_week_range


@pytest.fixture
def mock_setup_django():
    """setup_django 모듈 모킹"""
    sys.modules["setup_django"] = MagicMock()
    try:
        yield sys.modules["setup_django"]
    finally:
        # 테스트 후 정리
        del sys.modules["setup_django"]


@pytest.fixture
def user(db):
    """일반 User 객체 생성"""
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        group_id=1,
        email="test@example.com",
        username="test_user",
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
    """UserWeeklyTrendAdmin 인스턴스"""
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
def sample_weekly_user_stats():
    """테스트용 주간 사용자 통계 데이터"""
    return WeeklyUserStats(
        posts=20,
        new_posts=3,
        views=100,
        likes=10,
    )


@pytest.fixture
def sample_weekly_user_reminder():
    """테스트용 주간 사용자 리마인더 데이터"""
    return WeeklyUserReminder(
        title="Django 20주년 축하하기",
        days_ago=12,
    )


@pytest.fixture
def sample_weekly_trend_insight(sample_trend_analysis, sample_trending_items):
    """테스트용 주간 트렌드 인사이트 데이터"""
    return WeeklyTrendInsight(
        trending_summary=sample_trending_items,
        trend_analysis=sample_trend_analysis,
    )


@pytest.fixture
def sample_weekly_user_trend_insight(
    sample_trend_analysis,
    sample_trending_items,
    sample_weekly_user_stats,
    sample_weekly_user_reminder,
):
    """테스트용 사용자 주간 트렌드 인사이트 데이터"""
    return WeeklyUserTrendInsight(
        trending_summary=sample_trending_items,
        trend_analysis=sample_trend_analysis,
        user_weekly_stats=sample_weekly_user_stats,
        user_weekly_reminder=sample_weekly_user_reminder,
    )


@pytest.fixture
def sample_newsletter(user):
    """테스트용 뉴스레터 객체 생성"""
    return Newsletter(
        user_id=user.id,
        email_message=EmailMessage(
            to=[user.email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            subject="벨로그 대시보드 주간 뉴스레터 #1",
            text_body="Weekly Report Test content",
            html_body="<div>Weekly Report<br/>Velog Dashboard<br/>활동 리포트<br/>대시보드 보러가기</div>",
        ),
    )


@pytest.fixture
def sample_newsletters(sample_newsletter):
    """테스트용 뉴스레터 리스트 생성"""
    return [sample_newsletter]


@pytest.fixture
def weekly_trend(
    db, sample_weekly_trend_insight: WeeklyTrendInsight
) -> WeeklyTrend:
    """주간 트렌드 생성"""
    week_start, week_end = get_previous_week_range()

    return WeeklyTrend.objects.create(
        week_start_date=week_start,
        week_end_date=week_end,
        insight=sample_weekly_trend_insight.to_json_dict(),
    )


@pytest.fixture
def user_weekly_trend(
    db, user, sample_weekly_user_trend_insight: WeeklyUserTrendInsight
) -> UserWeeklyTrend:
    """사용자 주간 트렌드 생성"""
    week_start, week_end = get_previous_week_range()

    insight_dict = sample_weekly_user_trend_insight.to_json_dict()
    insight_dict["user_weekly_reminder"] = {}  # 주간 글 작성 사용자

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
def inactive_user_weekly_trend(
    db, user, sample_weekly_user_trend_insight: WeeklyUserTrendInsight
):
    """주간 글 미작성 사용자 주간 트렌드 생성"""
    week_start, week_end = get_previous_week_range()

    insight_dict = sample_weekly_user_trend_insight.to_json_dict()
    insight_dict["trending_summary"] = []
    insight_dict["trend_analysis"] = {}
    insight_dict["user_weekly_stats"]["new_posts"] = 0

    return UserWeeklyTrend.objects.create(
        user=user,
        week_start_date=week_start,
        week_end_date=week_end,
        insight=insight_dict,
    )


@pytest.fixture
def empty_insight_weekly_trend(db):
    """빈 인사이트를 가진 주간 트렌드"""
    week_start, week_end = get_previous_week_range()

    return WeeklyTrend.objects.create(
        week_start_date=week_start, week_end_date=week_end, insight={}
    )


@pytest.fixture
def mock_post():
    """테스트용 게시글 목록 응답 (get_trending_posts 용)"""
    return MagicMock(
        id="abc123",
        title="test title",
        views=100,
        likes=10,
        user=MagicMock(username="tester"),
        thumbnail="thumbnail",
        url_slug="test",
    )


@pytest.fixture
def mock_post_detail():
    """테스트용 게시글 본문 응답 (get_post 용)"""
    return MagicMock(body="test content")


@pytest.fixture
def mock_context(mock_post, mock_post_detail):
    """VelogClient 및 날짜 mock을 포함한 컨텍스트"""
    mock_velog_client = AsyncMock()
    mock_velog_client.get_trending_posts.return_value = [mock_post]
    mock_velog_client.get_post.return_value = mock_post_detail

    mock_context = MagicMock()
    mock_context.velog_client = mock_velog_client
    mock_context.week_start.date.return_value = "2025-07-21"
    mock_context.week_end.date.return_value = "2025-07-27"
    mock_context.week_end = datetime(2025, 7, 27)
    return mock_context


@pytest.fixture
def trending_post_data(mock_post, mock_post_detail):
    from insight.tasks.weekly_trend_analysis import TrendingPostData

    return TrendingPostData(post=mock_post, body=mock_post_detail.body)
