import importlib
import os
from unittest.mock import patch

import pytest

import modules.redis.config as redis_config


def test_blank_redis_integer_env_uses_defaults() -> None:
    """GitHub Actions 빈 secret 이 REDIS_PORT='' 로 주입돼도 기본값을 사용한다."""
    blank_integer_env = {
        "REDIS_PORT": "",
        "REDIS_DB": "",
        "REDIS_MAX_FAILED_QUEUE_SIZE": "",
        "RECLAIM_VISIBILITY_TIMEOUT_SEC": "",
        "RECLAIM_INTERVAL_SEC": "",
        "RECLAIM_MAX_RECLAIMS": "",
    }

    with patch.dict(os.environ, blank_integer_env):
        reloaded = importlib.reload(redis_config)

    try:
        assert reloaded.RedisConfig.PORT == 6379
        assert reloaded.RedisConfig.DB == 0
        assert reloaded.RedisConfig.MAX_FAILED_QUEUE_SIZE == 10000
        assert reloaded.RedisConfig.RECLAIM_VISIBILITY_TIMEOUT_SEC == 600
        assert reloaded.RedisConfig.RECLAIM_INTERVAL_SEC == 60
        assert reloaded.RedisConfig.RECLAIM_MAX_RECLAIMS == 3
    finally:
        importlib.reload(redis_config)


def test_invalid_redis_integer_env_still_raises_value_error() -> None:
    """숫자가 아닌 Redis 정수 env 는 조용히 기본값으로 숨기지 않는다."""
    with patch.dict(os.environ, {"REDIS_PORT": "not-a-number"}):
        with pytest.raises(ValueError):
            importlib.reload(redis_config)

    importlib.reload(redis_config)
