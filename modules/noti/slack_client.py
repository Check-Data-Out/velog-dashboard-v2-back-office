"""Slack 웹훅 간단 클라이언트.

- SLACK_OPS_WEBHOOK 환경변수 미설정 → no-op
- 동일 cooldown_key 는 cooldown_sec (기본 1800=30분) 이내 중복 전송 차단.
  Redis 에 ``vd2:ops:slack:cooldown:<key>`` 를 TTL 로 기록.
- 전송 실패 시 cooldown 키를 삭제해 다음 알림이 묵살되지 않도록 한다.
- webhook 은 HTTPS 만 허용 (운영 실수 방어).
"""

import json
import logging
from urllib import request as urlrequest
from urllib.parse import urlparse

import environ

logger = logging.getLogger(__name__)

env = environ.Env()
COOLDOWN_PREFIX = "vd2:ops:slack:cooldown:"
DEFAULT_COOLDOWN_SEC = 1800


def _webhook_url() -> str:
    value = env("SLACK_OPS_WEBHOOK", default="")
    return str(value).strip()


def _cooldown_active(
    redis_client: object, cooldown_key: str | None, cooldown_sec: int
) -> bool:
    """cooldown 상태. 이미 있으면 True, 새로 획득하면 False.

    Redis 장애 시 fail-closed: cooldown 을 보장할 수 없으면 True(차단) 반환해
    의도치 않은 연속 전송을 막는다.
    """
    if not cooldown_key or redis_client is None:
        return False
    key = f"{COOLDOWN_PREFIX}{cooldown_key}"
    try:
        # SET NX EX: 없을 때만 설정 + TTL. 이미 있으면 False.
        acquired = redis_client.client.set(key, "1", nx=True, ex=cooldown_sec)  # type: ignore[attr-defined]
        return bool(acquired is None or acquired is False)
    except Exception as e:
        logger.warning(f"slack cooldown check failed (fail-closed): {e}")
        return True


def _release_cooldown(redis_client: object, cooldown_key: str | None) -> None:
    """전송 실패 시 cooldown 키 삭제 — 다음 요청이 바로 재시도 가능하도록."""
    if not cooldown_key or redis_client is None:
        return
    try:
        redis_client.client.delete(f"{COOLDOWN_PREFIX}{cooldown_key}")  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning(f"slack cooldown release failed: {e}")


def _is_valid_https_webhook(url: str) -> bool:
    """운영 실수 방지 — HTTPS scheme 만 허용."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def notify_ops(
    text: str,
    *,
    cooldown_key: str | None = None,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
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
    if not _is_valid_https_webhook(webhook):
        logger.error(
            "SLACK_OPS_WEBHOOK scheme is not HTTPS — skipping for safety"
        )
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
            # 실패 시 cooldown 해제 — 30분 묵살 방지.
            _release_cooldown(redis_client, cooldown_key)
            logger.warning(f"slack notify non-2xx: {resp.status}")
            return False
    except Exception as e:
        _release_cooldown(redis_client, cooldown_key)
        logger.error(f"slack notify failed: {e}")
        return False
