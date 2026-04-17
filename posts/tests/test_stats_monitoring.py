"""Phase 1 — PostStatsMonitoringManager 및 PostAdmin StatsStatusFilter 테스트."""

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory

from posts.admin import PostAdmin, StatsStatusFilter
from posts.models import Post, PostDailyStatistics
from users.models import User
from utils.utils import get_local_now_date


@pytest.fixture
def user(db):
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="tok",
        refresh_token="tok",
        group_id=1,
        email="stats-monitor@example.com",
        username="stats-monitor",
        is_active=True,
    )


@pytest.fixture
def post_with_today_stats(db, user):
    post = Post.objects.create(
        post_uuid=uuid.uuid4(), user=user, title="with-today", is_active=True
    )
    PostDailyStatistics.objects.create(
        post=post,
        date=get_local_now_date(),
        daily_view_count=1,
        daily_like_count=0,
    )
    return post


@pytest.fixture
def post_missing_today(db, user):
    post = Post.objects.create(
        post_uuid=uuid.uuid4(),
        user=user,
        title="missing-today",
        is_active=True,
    )
    PostDailyStatistics.objects.create(
        post=post,
        date=get_local_now_date() - timedelta(days=1),
        daily_view_count=1,
        daily_like_count=0,
    )
    return post


@pytest.fixture
def post_inactive_no_stats(db, user):
    return Post.objects.create(
        post_uuid=uuid.uuid4(), user=user, title="inactive", is_active=False
    )


class TestPostStatsMonitoringManager:
    def test_missing_today_stats_returns_active_posts_without_today_stats_only(
        self, post_missing_today, post_with_today_stats, post_inactive_no_stats
    ):
        ids = set(
            Post.stats_monitor.missing_today_stats().values_list(
                "pk", flat=True
            )
        )
        assert post_missing_today.pk in ids
        assert post_with_today_stats.pk not in ids
        assert post_inactive_no_stats.pk not in ids

    def test_get_posts_missing_today_stats_queryset_classmethod_delegates_to_manager(
        self, post_missing_today
    ):
        classmethod_ids = set(
            Post.get_posts_missing_today_stats_queryset().values_list(
                "pk", flat=True
            )
        )
        manager_ids = set(
            Post.stats_monitor.missing_today_stats().values_list(
                "pk", flat=True
            )
        )
        assert classmethod_ids == manager_ids
        assert post_missing_today.pk in classmethod_ids


class TestStatsStatusFilter:
    def test_filter_restricts_to_missing_today_posts(
        self, db, post_missing_today, post_with_today_stats
    ):
        factory = RequestFactory()
        request = factory.get(
            "/admin/posts/post/", {"stats_status": "missing"}
        )
        flt = StatsStatusFilter(
            request,
            {"stats_status": ["missing"]},
            Post,
            PostAdmin,
        )
        qs = flt.queryset(request, Post.objects.all())
        ids = set(qs.values_list("pk", flat=True))
        assert post_missing_today.pk in ids
        assert post_with_today_stats.pk not in ids

    def test_filter_noop_when_value_missing(
        self, db, post_missing_today, post_with_today_stats
    ):
        factory = RequestFactory()
        request = factory.get("/admin/posts/post/")
        flt = StatsStatusFilter(request, {}, Post, PostAdmin)
        qs = flt.queryset(request, Post.objects.all())
        ids = set(qs.values_list("pk", flat=True))
        assert post_missing_today.pk in ids
        assert post_with_today_stats.pk in ids
