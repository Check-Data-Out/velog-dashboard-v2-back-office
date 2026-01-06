import environ

env = environ.Env()


class RedisConfig:
    """Redis configuration for consumer."""

    HOST = env("REDIS_HOST", default="localhost")
    PORT = env.int("REDIS_PORT", default=6379)
    PASSWORD = env("REDIS_PASSWORD", default="notion-check-plz")
    DB = env.int("REDIS_DB", default=0)

    # Queue names
    QUEUE_STATS_REFRESH = "vd2:queue:stats-refresh"
    QUEUE_STATS_REFRESH_PROCESSING = "vd2:queue:stats-refresh:processing"
    QUEUE_STATS_REFRESH_FAILED = "vd2:queue:stats-refresh:failed"

    # Consumer settings
    BLOCKING_TIMEOUT = 5  # seconds for BRPOP
    MAX_RETRIES = 3  # maximum retry attempts
    RETRY_BACKOFF_BASE = 2  # exponential backoff base (seconds)

    # DLQ (Dead Letter Queue) settings
    # Failed queue 최대 크기 - 초과 시 오래된 메시지부터 삭제
    # https://redis.io/glossary/redis-queue/
    MAX_FAILED_QUEUE_SIZE = env.int(
        "REDIS_MAX_FAILED_QUEUE_SIZE", default=10000
    )


class ConsumerConfig:
    """Consumer process configuration."""

    PROCESS_NAME = "stats-refresh-consumer"
    LOG_LEVEL = env("CONSUMER_LOG_LEVEL", default="INFO")
    GRACEFUL_SHUTDOWN_TIMEOUT = env.int(
        "CONSUMER_GRACEFUL_SHUTDOWN_TIMEOUT", default=30
    )
