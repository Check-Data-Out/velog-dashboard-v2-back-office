"""Post 통계 모니터링용 Custom Manager.

Plan.md Phase 1: Mixin 상속 대신 Manager 분리로 circular import 제거.
AGENTS.md "함수 내부 import 금지" 준수를 위해 PostDailyStatistics 참조는
`apps.get_model` registry 조회로 해결한다.
"""

from django.db import models
from django.db.models import Exists, OuterRef

from utils.utils import get_local_now_date


class PostStatsMonitoringManager(models.Manager):
    """Post 의 오늘 통계 유무를 질의하는 전용 Manager.

    사용처:
        - Post Admin 의 "오늘 통계 누락" 필터
        - 배치(`aggregate_batch`) 완료 후 알림 임계 판단
        - `Post.get_posts_missing_today_stats_queryset()` classmethod wrapper
    """

    def missing_today_stats(self) -> models.QuerySet:
        """활성(is_active=True) 포스트 중 오늘자 PostDailyStatistics 가 없는 것."""
        PostDailyStatistics = self.model._meta.apps.get_model(
            "posts", "PostDailyStatistics"
        )
        today_start = get_local_now_date()
        today_stats = PostDailyStatistics.objects.filter(
            post_id=OuterRef("pk"),
            date__gte=today_start,
        )
        return (
            self.filter(is_active=True)
            .annotate(_has_today=Exists(today_stats))
            .filter(_has_today=False)
        )
