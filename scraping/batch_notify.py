"""배치 완료 후 Slack 알림 훅.

aggregate_batch.py 의 ``import setup_django`` (sys.path 기반 스크립트 import) 가
테스트에서 모듈로 import 불가하기 때문에 분리한 파일. Django setup 이 끝난
이후에만 호출되도록 ``aggregate_batch.main()`` 에서 지연 import 하여 사용.
"""

import logging

import environ

logger = logging.getLogger("scraping")
env = environ.Env()


def notify_after_batch() -> None:
    """'오늘 통계 누락' 포스트 수가 임계 초과면 Slack 알림."""
    from modules.noti.slack_client import notify_ops
    from modules.redis.client import get_redis_client
    from posts.models import Post

    threshold = env.int("MISSING_POSTS_THRESHOLD", default=100)
    missing = Post.get_posts_missing_today_stats_queryset().count()
    if missing <= threshold:
        logger.info(
            f"batch notify: missing={missing} under threshold={threshold}"
        )
        return

    text = f"[velog-dashboard-v2] 오늘 통계 누락 포스트 {missing}건이 임계({threshold}) 초과"
    try:
        redis_client = None
        try:
            redis_client = get_redis_client()
        except Exception as e:
            logger.warning(f"batch notify: redis unavailable ({e})")

        notify_ops(
            text,
            cooldown_key="aggregate-batch:missing-posts",
            redis_client=redis_client,
        )
    except Exception as e:
        logger.warning(f"batch notify failed: {e}")
