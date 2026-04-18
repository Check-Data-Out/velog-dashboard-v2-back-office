"""aggregate_batch notify_after_batch 테스트 — 임계 초과 시에만 notify_ops 호출."""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from posts.models import Post, PostDailyStatistics
from scraping.batch_notify import notify_after_batch
from users.models import User
from utils.utils import get_local_now_date

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="t",
        refresh_token="t",
        group_id=1,
        email="b@x.com",
        username="b",
        is_active=True,
    )


def _make_post(user, idx, *, with_today_stats: bool):
    post = Post.objects.create(
        post_uuid=uuid.uuid4(),
        user=user,
        title=f"p-{idx}",
        is_active=True,
    )
    # with_today_stats=False 면 어제 날짜로만 stats 생성 → 오늘 누락 대상
    date = (
        get_local_now_date()
        if with_today_stats
        else get_local_now_date() - timedelta(days=1)
    )
    PostDailyStatistics.objects.create(
        post=post, date=date, daily_view_count=1, daily_like_count=0
    )
    return post


class TestNotifyAfterBatch:
    def test_notifies_when_over_threshold(self, user, monkeypatch):
        # 3 건을 누락 상태로 만들고 임계 2 로 설정
        for i in range(3):
            _make_post(user, i, with_today_stats=False)
        monkeypatch.setenv("MISSING_POSTS_THRESHOLD", "2")
        with patch(
            "modules.noti.slack_client.notify_ops", return_value=True
        ) as mock_notify:
            with patch(
                "modules.redis.client.get_redis_client", return_value=None
            ):
                notify_after_batch()
        mock_notify.assert_called_once()
        text_arg = mock_notify.call_args[0][0]
        assert "누락" in text_arg

    def test_skips_when_under_threshold(self, user, monkeypatch):
        _make_post(user, 0, with_today_stats=False)
        monkeypatch.setenv("MISSING_POSTS_THRESHOLD", "100")
        with patch("modules.noti.slack_client.notify_ops") as mock_notify:
            notify_after_batch()
        mock_notify.assert_not_called()
