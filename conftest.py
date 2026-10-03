import os

import pytest
import sentry_sdk
from django.conf import settings

from backoffice.db_guard import is_safe_test_db_host


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix):
    """테스트 DB 생성 직전, 로컬이 아닌 HOST 면 세션을 중단한다."""
    # HOST 가 비면 libpq 가 PGHOST 를 쓰므로 함께 판정한다
    host = settings.DATABASES["default"]["HOST"] or os.environ.get(
        "PGHOST", ""
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
