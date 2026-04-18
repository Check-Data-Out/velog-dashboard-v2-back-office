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


def _coerce_int(value: object) -> int:
    """None / 비숫자 값을 0 으로 정규화."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def ensure_envelope(raw: dict) -> dict:
    """누락된 필드를 consumer 측에서 보강. 기존 필드는 덮어쓰지 않음.

    숫자 필드(retryCount, reclaimedCount) 는 외부 producer 가 손상된 값을
    넣은 경우에 대비해 정규화까지 수행 — reclaimer/consumer 하류에서 이 함수를
    통과한 뒤에는 int 임을 전제할 수 있다.
    """
    msg = dict(raw)  # shallow copy
    now_iso = get_local_now().isoformat()

    msg.setdefault("requestId", str(uuid.uuid4()))
    msg.setdefault("enqueuedAt", msg.get("requestedAt", now_iso))
    msg.setdefault("requestedBy", None)
    msg["retryCount"] = _coerce_int(msg.get("retryCount"))
    msg["reclaimedCount"] = _coerce_int(msg.get("reclaimedCount"))
    return msg
