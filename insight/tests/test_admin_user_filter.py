from datetime import timedelta

import pytest

from insight.admin import UserFilter
from insight.models import UserWeeklyTrend
from users.models import User


@pytest.mark.django_db
class TestUserFilter:
    """UserFilter 테스트"""

    def test_lookups(self) -> None:
        """lookups 메소드 테스트"""
        user_filter = UserFilter(
            request=None, params={}, model=None, model_admin=None
        )

        lookups = user_filter.lookups(None, None)
        assert len(lookups) == 3
        assert ("has_posts", "분석된 게시글이 있는 사용자") in lookups
        assert ("no_posts", "분석된 게시글이 없는 사용자") in lookups
        assert ("high_keywords", "분석된 키워드가 있는 사용자") in lookups

    def test_queryset_has_posts(
        self, user_weekly_trend: UserWeeklyTrend
    ) -> None:
        """has_posts 필터 테스트"""
        user_filter = UserFilter(
            request=None,
            params={"user_group": "has_posts"},
            model=None,
            model_admin=None,
        )

        filtered_qs = user_filter.queryset(
            None, user_weekly_trend.__class__.objects.all()
        )
        assert user_weekly_trend in filtered_qs

    def test_queryset_no_posts(
        self, user: User, user_weekly_trend: UserWeeklyTrend
    ) -> None:
        """no_posts 필터 테스트"""

        # 게시글이 없는 사용자 트렌드 생성
        empty_trend = UserWeeklyTrend.objects.create(
            user=user,
            week_start_date=user_weekly_trend.week_start_date
            - timedelta(days=14),
            week_end_date=user_weekly_trend.week_end_date - timedelta(days=14),
            insight={"trend_analysis": {"hot_keywords": []}},
        )

        user_filter = UserFilter(
            request=None,
            params={"user_group": "no_posts"},
            model=None,
            model_admin=None,
        )

        filtered_qs = user_filter.queryset(None, UserWeeklyTrend.objects.all())
        assert empty_trend in filtered_qs
        assert user_weekly_trend not in filtered_qs

    def test_queryset_high_keywords(
        self, user_weekly_trend: UserWeeklyTrend
    ) -> None:
        """high_keywords 필터 테스트"""
        user_filter = UserFilter(
            request=None,
            params={"user_group": "high_keywords"},
            model=None,
            model_admin=None,
        )

        filtered_qs = user_filter.queryset(
            None, user_weekly_trend.__class__.objects.all()
        )
        assert user_weekly_trend in filtered_qs

    def test_queryset_no_filter(
        self, user_weekly_trend: UserWeeklyTrend
    ) -> None:
        """필터 없음 테스트"""
        user_filter = UserFilter(
            request=None, params={}, model=None, model_admin=None
        )

        filtered_qs = user_filter.queryset(
            None, user_weekly_trend.__class__.objects.all()
        )
        assert user_weekly_trend in filtered_qs
