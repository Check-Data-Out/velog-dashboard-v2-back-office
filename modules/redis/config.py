import base64

import environ

env = environ.Env()


def _env_int(name: str, default: int) -> int:
    value = env(name, default=None)
    if value in (None, ""):
        return default
    return int(value)


def _resolve_password() -> str:
    # django-environ 은 .env 파싱 시 `#` 이후를 주석으로 잘라버리므로,
    # `#` 이 포함된 비밀번호는 REDIS_PASSWORD_B64 (base64) 로 제공한다.
    b64: str = env("REDIS_PASSWORD_B64", default="")
    if b64:
        return base64.b64decode(b64).decode("utf-8")
    # 기본값은 빈 문자열. .env 미설정 시 실제처럼 보이는 기본 비밀번호가 그대로
    # 운영에 유출되는 것을 방지한다. Redis 서버가 AUTH 요구 시 명시적 실패로 surface.
    raw: str = env("REDIS_PASSWORD", default="")
    return raw


class RedisConfig:
    """Redis configuration for queue client/consumer/monitor."""

    HOST = env("REDIS_HOST", default="localhost")
    PORT = _env_int("REDIS_PORT", default=6379)
    PASSWORD = _resolve_password()
    DB = _env_int("REDIS_DB", default=0)

    # Queue names (단일 소비자 + pending/processing/DLQ 3종)
    QUEUE_STATS_REFRESH = "vd2:queue:stats-refresh"
    QUEUE_STATS_REFRESH_PROCESSING = "vd2:queue:stats-refresh:processing"
    QUEUE_STATS_REFRESH_FAILED = "vd2:queue:stats-refresh:failed"

    # 연결 인자 (redis.Redis kwargs)
    # SOCKET_TIMEOUT 은 BLOCKING_TIMEOUT 보다 커야 한다 (BLMOVE 정상 대기 보호).
    SOCKET_TIMEOUT = 10
    SOCKET_CONNECT_TIMEOUT = 5
    SOCKET_KEEPALIVE = True
    HEALTH_CHECK_INTERVAL = 30
    # ConnectionError 만 1회 재시도. TimeoutError 는 명령 적용 여부가 불명이라
    # 비멱등 LPUSH 중복을 피하기 위해 제외한다.
    RETRY_ATTEMPTS = 1
    RETRY_BACKOFF_BASE_SEC = 0.5
    RETRY_BACKOFF_CAP_SEC = 2

    # Consumer settings
    BLOCKING_TIMEOUT = 5  # seconds for BRPOP/BLMOVE
    MAX_RETRIES = 3  # process_with_retry 최대 재시도
    RETRY_BACKOFF_BASE = 2  # exponential backoff base (seconds)
    CAS_MAX_ATTEMPTS = 3  # replace_processing_head WATCH/MULTI 재시도 상한

    # DLQ 크기 제한 (초과 시 오래된 것부터 삭제)
    MAX_FAILED_QUEUE_SIZE = _env_int(
        "REDIS_MAX_FAILED_QUEUE_SIZE", default=10000
    )

    # Reclaimer — processing 큐 stuck 메시지 복구 설정
    RECLAIM_VISIBILITY_TIMEOUT_SEC = _env_int(
        "RECLAIM_VISIBILITY_TIMEOUT_SEC", default=600
    )
    RECLAIM_INTERVAL_SEC = _env_int("RECLAIM_INTERVAL_SEC", default=60)
    RECLAIM_MAX_RECLAIMS = _env_int("RECLAIM_MAX_RECLAIMS", default=3)
