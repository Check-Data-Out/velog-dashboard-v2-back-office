"""Consumer 프로세스 전용 설정.

RedisConfig 는 modules.redis.config 로 이동. 여기서는 하위호환을 위해
re-export 만 유지. 신규 코드는 ``from modules.redis.config import RedisConfig`` 사용 권장.
"""

import environ

from modules.redis.config import RedisConfig  # noqa: F401  (re-export)

env = environ.Env()


class ConsumerConfig:
    """Consumer 프로세스 공통 설정."""

    PROCESS_NAME = "stats-refresh-consumer"
    LOG_LEVEL = env("CONSUMER_LOG_LEVEL", default="INFO")
    GRACEFUL_SHUTDOWN_TIMEOUT = env.int(
        "CONSUMER_GRACEFUL_SHUTDOWN_TIMEOUT", default=30
    )
    # Phase 7 준비: 연속 에러 허용치 (5 → 30 상향, env override 가능)
    MAX_CONSECUTIVE_ERRORS = env.int(
        "CONSUMER_MAX_CONSECUTIVE_ERRORS", default=30
    )
    # Phase 7 /healthz 포트 (내부 bind only)
    HEALTHZ_PORT = env.int("CONSUMER_HEALTHZ_PORT", default=8081)
    HEALTHZ_STALE_THRESHOLD_SEC = env.int(
        "CONSUMER_HEALTHZ_STALE_THRESHOLD_SEC", default=60
    )
