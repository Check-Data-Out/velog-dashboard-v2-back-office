import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from posts.models import PostDailyStatistics


def test_same_post_and_date_is_rejected(post_stats_factory):
    """같은 게시글·날짜의 두 번째 행을 DB 가 거부하는지.

    get_or_create 는 DB 가 유일성을 강제할 때만 경합에 안전하다. 강제하지 않으면
    두 프로세스가 같은 게시글을 동시에 처리할 때 같은 날 행이 두 개 생기고, 그 뒤
    get_or_create 가 MultipleObjectsReturned 로 그날 갱신을 계속 실패한다.
    """
    first = post_stats_factory(date=timezone.now())

    with pytest.raises(IntegrityError), transaction.atomic():
        PostDailyStatistics.objects.create(post=first.post, date=first.date)
