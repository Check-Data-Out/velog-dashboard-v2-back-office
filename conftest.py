import pytest
import sentry_sdk


@pytest.fixture(autouse=True)
def _disable_sentry(monkeypatch):
    """모든 테스트에서 Sentry 이벤트 전송을 완전 차단."""
    monkeypatch.setattr(sentry_sdk, "capture_exception", lambda *a, **kw: None)
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **kw: None)
