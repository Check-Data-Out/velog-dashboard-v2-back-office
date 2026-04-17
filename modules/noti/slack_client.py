"""Slack 웹훅 간단 클라이언트 (Plan.md Phase 8 / F9).

- SLACK_OPS_WEBHOOK 환경변수 미설정 → no-op
- 동일 cooldown_key 는 cooldown_sec (기본 1800=30분) 이내 중복 전송 차단
  Redis 에 `vd2:ops:slack:cooldown:<key>` 를 TTL 로 기록
"""

import json
import logging
from urllib import request as urlrequest

import environ

logger = logging.getLogger(__name__)

env = environ.Env()
_COOLDOWN_PREFIX = "vd2:ops:slack:cooldown:"
_DEFAULT_COOLDOWN_SEC = 1800


def _webhook_url() -> str:
    value = env("SLACK_OPS_WEBHOOK", default="")
    return str(value).strip()


def _cooldown_active(
    redis_client: object, cooldown_key: str | None, cooldown_sec: int
) -> bool:
    """cooldown_key 가 주어지고 Redis 에 이미 존재하면 True 반환. 없으면 SET 후 False."""
    if not cooldown_key or redis_client is None:
        return False
    key = f"{_COOLDOWN_PREFIX}{cooldown_key}"
    try:
        # SET NX EX: 없을 때만 설정 + TTL. 이미 있으면 False.
        acquired = redis_client.client.set(key, "1", nx=True, ex=cooldown_sec)  # type: ignore[attr-defined]
        return bool(acquired is None or acquired is False)
    except Exception as e:
        logger.warning(f"slack cooldown check failed: {e}")
        return False


def notify_ops(
    text: str,
    *,
    cooldown_key: str | None = None,
    cooldown_sec: int = _DEFAULT_COOLDOWN_SEC,
    redis_client: object = None,
) -> bool:
    """운영 Slack 채널로 단순 텍스트 알림.

    Returns:
        True if sent, False if skipped (webhook 미설정/cooldown).
    """
    webhook = _webhook_url()
    if not webhook:
        logger.debug("SLACK_OPS_WEBHOOK not set — skipping notification")
        return False

    if _cooldown_active(redis_client, cooldown_key, cooldown_sec):
        logger.info(f"slack notify skipped (cooldown: {cooldown_key})")
        return False

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urlrequest.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=5) as resp:
            if 200 <= resp.status < 300:
                return True
            logger.warning(f"slack notify non-2xx: {resp.status}")
            return False
    except Exception as e:
        logger.error(f"slack notify failed: {e}")
        return False
