"""Stats refresh queue 메시지 envelope 헬퍼.

외부 producer 가 부분 envelope 만 보내도 consumer 측에서 `requestId`,
`enqueuedAt`, `reclaimedCount`, `requestedBy` 를 자동 보강하여 downstream
(reclaimer, lifecycle 추적) 이 동일 스키마로 동작하도록 한다.

사용 시점:
    - producer 측 (admin update_stats) 에서 큐 푸시 전: build_envelope
    - consumer 측 BLMOVE 직후: ensure_envelope
"""

import uuid

from utils.utils import get_local_now


def build_envelope(
    user_id: int,
    requested_by: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Producer 측에서 완전한 envelope 을 만들어 큐에 넣는 헬퍼."""
    now_iso = get_local_now().isoformat()
    return {
        "requestId": request_id or str(uuid.uuid4()),
        "userId": user_id,
        "requestedAt": now_iso,
        "requestedBy": requested_by,
        "retryCount": 0,
        "reclaimedCount": 0,
        "enqueuedAt": now_iso,
        "lastAttemptAt": None,
    }


def _coerce_non_negative_int(value: object) -> int:
    """None / 비숫자 / 음수 값을 0 으로 정규화."""
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def ensure_envelope(raw: dict) -> dict:
    """누락되거나 손상된 필드를 consumer 측에서 보강.

    숫자 필드는 음수/None/비숫자를 0 으로 클램프, 필수 문자열 필드는
    None/빈값이 들어온 경우에도 값을 채운다 (`setdefault` 는 falsy 통과하므로
    명시적 검사 필요). 하류(reclaimer, consumer) 는 이 함수를 통과한 뒤
    필드가 정상 타입임을 전제한다.
    """
    msg = dict(raw)  # shallow copy
    now_iso = get_local_now().isoformat()

    if not msg.get("requestId"):
        msg["requestId"] = str(uuid.uuid4())
    if not msg.get("enqueuedAt"):
        msg["enqueuedAt"] = msg.get("requestedAt") or now_iso
    if "requestedBy" not in msg:
        msg["requestedBy"] = None
    msg["retryCount"] = _coerce_non_negative_int(msg.get("retryCount"))
    msg["reclaimedCount"] = _coerce_non_negative_int(msg.get("reclaimedCount"))
    return msg
