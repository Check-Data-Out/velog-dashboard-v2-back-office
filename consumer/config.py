import environ

from modules.redis.config import RedisConfig  # noqa: F401  re-export

env = environ.Env()


class ConsumerConfig:
    """Consumer 프로세스 공통 설정."""

    PROCESS_NAME = "stats-refresh-consumer"
    LOG_LEVEL = env("CONSUMER_LOG_LEVEL", default="INFO")
    GRACEFUL_SHUTDOWN_TIMEOUT = env.int(
        "CONSUMER_GRACEFUL_SHUTDOWN_TIMEOUT", default=30
    )
    # 연속 에러 허용치 — 초과 시 하드 종료. Redis 블립에 과민 반응하지 않도록 30 기본.
    MAX_CONSECUTIVE_ERRORS = env.int(
        "CONSUMER_MAX_CONSECUTIVE_ERRORS", default=30
    )
    # /healthz 포트 (내부 bind only)
    HEALTHZ_PORT = env.int("CONSUMER_HEALTHZ_PORT", default=8081)
    HEALTHZ_STALE_THRESHOLD_SEC = env.int(
        "CONSUMER_HEALTHZ_STALE_THRESHOLD_SEC", default=60
    )
