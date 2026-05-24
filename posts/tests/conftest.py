import uuid
from datetime import datetime

import pytest

from posts.models import Post, PostDailyStatistics
from users.models import User


@pytest.fixture
def post_stats_factory(db):
    """임의 date 의 PostDailyStatistics 를 생성하는 factory fixture."""

    def _make(
        date: datetime,
        daily_view_count: int = 1,
        daily_like_count: int = 0,
        title: str = "factory",
    ) -> PostDailyStatistics:
        user = User.objects.create(
            velog_uuid=uuid.uuid4(),
            access_token="tok",
            refresh_token="tok",
        )
        post = Post.objects.create(
            post_uuid=uuid.uuid4(),
            user=user,
            title=title,
            is_active=True,
        )
        return PostDailyStatistics.objects.create(
            post=post,
            date=date,
            daily_view_count=daily_view_count,
            daily_like_count=daily_like_count,
        )

    return _make
