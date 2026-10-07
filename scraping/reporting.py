"""스크래퍼 실패를 Sentry 로 보고하는 헬퍼.

velog API(네트워크) 실패는 알려진 원인(cause)별 고정 fingerprint 로 묶고
cause 당 REPORT_WINDOW_SEC 윈도 안에서는 1건만 보낸다(억제 건수는 다음
이벤트의 tag/extra 로). 그 외(source 없음·미지 원인)는 기본 그룹핑으로
그대로 보낸다 — 오분류·과억제 방지.

``sentry_sdk.capture_exception`` 은 속성 접근으로 호출한다(테스트 monkeypatch 호환).
"""

import time

import aiohttp
import sentry_sdk

from utils.utils import get_local_now

SOURCE_VELOG_API = "velog-api"
REPORT_WINDOW_SEC = 600

_last_reported_at: dict[str, float] = {}
_suppressed: dict[str, int] = {}
_suppressed_since: dict[str, str] = {}


def reset_report_window() -> None:
    """테스트용 — 윈도/억제 상태 초기화."""
    _last_reported_at.clear()
    _suppressed.clear()
    _suppressed_since.clear()


def cause_for(exc: BaseException) -> str | None:
    """velog API 호출 실패의 알려진 원인 분류. 모르면 None (기본 그룹핑).

    aiohttp 계층: ClientSSLError ⊂ ClientConnectorError ⊂ ClientOSError ⊂
    ClientConnectionError 이므로 구체적인 것부터 검사하고, 연결 계열의
    나머지는 ClientConnectionError 로 묶는다. ServerTimeoutError ⊂ TimeoutError.
    """
    if isinstance(exc, aiohttp.ClientSSLError):
        return "ssl"
    if isinstance(exc, (aiohttp.ServerTimeoutError, TimeoutError)):
        return "timeout"
    if isinstance(exc, aiohttp.ClientConnectorDNSError):
        return "dns"
    if isinstance(exc, aiohttp.ClientConnectorError):
        return "connect"
    if isinstance(exc, aiohttp.ClientPayloadError):
        return "payload"
    # ServerDisconnectedError / ClientOSError / ClientConnectionResetError 등
    # 연결 후 끊김 계열 — ClientConnectionError 로 묶는다.
    if isinstance(exc, aiohttp.ClientConnectionError):
        return "connection"
    if isinstance(exc, aiohttp.ClientResponseError):
        return "http"
    if isinstance(exc, KeyError):
        return "malformed"
    return None


def capture_scraper_failure(
    exc: BaseException,
    *,
    source: str | None = None,
    **tags: str | int | None,
) -> None:
    """스크래퍼 실패 1건을 Sentry 이벤트로 보고한다.

    Args:
        exc: 보고할 예외(최종 실패 1건 — 재시도 중간 단계에서는 호출 금지).
        source: ``SOURCE_VELOG_API`` 이면 cause 분류 + fingerprint + 윈도
            dedupe. None 이면 ``exc.__cause__`` 가 velog 네트워크 예외일 때만
            (VelogFetchError 체인) 같은 처리, 아니면 기본 그룹핑.
        **tags: Sentry tag. 값이 None 인 항목은 생략한다.
    """
    tag_values: dict[str, str] = {
        key: str(value) for key, value in tags.items() if value is not None
    }
    cause: str | None = None
    if source == SOURCE_VELOG_API:
        cause = cause_for(exc)
    elif source is None and exc.__cause__ is not None:
        cause = cause_for(exc.__cause__)
    if cause is None:
        sentry_sdk.capture_exception(exc, tags=tag_values)
        return

    now = time.monotonic()
    last = _last_reported_at.get(cause)
    if last is not None and now - last < REPORT_WINDOW_SEC:
        _suppressed[cause] = _suppressed.get(cause, 0) + 1
        _suppressed_since.setdefault(cause, get_local_now().isoformat())
        return

    _last_reported_at[cause] = now
    tag_values["scraper.cause"] = cause
    fingerprint = ["scraper", SOURCE_VELOG_API, cause]
    suppressed = _suppressed.pop(cause, 0)
    if suppressed:
        tag_values["scraper.suppressed"] = str(suppressed)
        sentry_sdk.capture_exception(
            exc,
            fingerprint=fingerprint,
            tags=tag_values,
            extras={"suppressed_since": _suppressed_since.pop(cause, None)},
        )
        return
    sentry_sdk.capture_exception(exc, fingerprint=fingerprint, tags=tag_values)
