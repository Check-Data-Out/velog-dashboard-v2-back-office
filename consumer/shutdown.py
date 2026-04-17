"""Shutdown 신호를 main thread 가 수신하면 daemon thread 로 전파하는 Event.

Plan.md Phase 5/7 전제: Python signal 은 main thread 에만 도착하므로,
reclaimer/healthz 같은 daemon thread 에 종료 의도를 알리려면 threading.Event 사용.
"""

import threading

_shutdown_event: threading.Event | None = None


def get_shutdown_event() -> threading.Event:
    """싱글톤 Event 반환 (프로세스 1개당 1개)."""
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = threading.Event()
    return _shutdown_event


def reset_shutdown_event() -> None:
    """테스트용."""
    global _shutdown_event
    _shutdown_event = None
