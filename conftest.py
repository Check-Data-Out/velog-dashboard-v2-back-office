import os

import pytest
import sentry_sdk
from django.conf import settings

from backoffice.db_guard import is_safe_test_db_host, resolve_test_db_host
from scraping.reporting import reset_report_window


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix):
    """테스트 DB 생성 직전, 로컬이 아닌 HOST 면 세션을 중단한다."""
    host = resolve_test_db_host(
        settings.DATABASES["default"]["HOST"], dict(os.environ)
    )
    if not is_safe_test_db_host(host):
        pytest.exit(
            f"테스트 DB HOST 가 로컬이 아닙니다: {host!r}. 운영 접속정보로 pytest 실행 금지.",
            returncode=1,
        )


@pytest.fixture(autouse=True)
def _disable_sentry(monkeypatch):
    """모든 테스트에서 Sentry 이벤트 전송을 완전 차단."""
    monkeypatch.setattr(sentry_sdk, "capture_exception", lambda *a, **kw: None)
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **kw: None)


@pytest.fixture(autouse=True)
def _reset_report_window():
    """스크래퍼 보고 헬퍼의 윈도/억제 상태가 테스트 간에 누수되지 않도록."""
    reset_report_window()
    yield
    reset_report_window()
