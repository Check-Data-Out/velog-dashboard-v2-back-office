"""Redis/Queue 설정.

consumer 패키지에서 이곳으로 이동. consumer 는 modules 에 의존하는
것이 맞고, modules 가 consumer 를 역참조하는 구조를 정리하기 위한 것.
"""

import environ

env = environ.Env()


class RedisConfig:
    """Redis configuration for queue client/consumer/monitor."""

    HOST = env("REDIS_HOST", default="localhost")
    PORT = env.int("REDIS_PORT", default=6379)
    PASSWORD = env("REDIS_PASSWORD", default="notion-check-plz")
    DB = env.int("REDIS_DB", default=0)

    # Queue names (단일 소비자 + pending/processing/DLQ 3종)
    QUEUE_STATS_REFRESH = "vd2:queue:stats-refresh"
    QUEUE_STATS_REFRESH_PROCESSING = "vd2:queue:stats-refresh:processing"
    QUEUE_STATS_REFRESH_FAILED = "vd2:queue:stats-refresh:failed"

    # Consumer settings
    BLOCKING_TIMEOUT = 5  # seconds for BRPOP/BLMOVE
    MAX_RETRIES = 3  # process_with_retry 최대 재시도
    RETRY_BACKOFF_BASE = 2  # exponential backoff base (seconds)

    # DLQ 크기 제한 (초과 시 오래된 것부터 삭제)
    MAX_FAILED_QUEUE_SIZE = env.int(
        "REDIS_MAX_FAILED_QUEUE_SIZE", default=10000
    )

    # Reclaimer — processing 큐 stuck 메시지 복구 설정
    RECLAIM_VISIBILITY_TIMEOUT_SEC = env.int(
        "RECLAIM_VISIBILITY_TIMEOUT_SEC", default=600
    )
    RECLAIM_INTERVAL_SEC = env.int("RECLAIM_INTERVAL_SEC", default=60)
    RECLAIM_MAX_RECLAIMS = env.int("RECLAIM_MAX_RECLAIMS", default=3)
