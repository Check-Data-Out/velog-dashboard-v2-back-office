import pytest
import sentry_sdk
from django.conf import settings
from sentry_sdk.integrations import logging as sentry_logging

from backoffice.settings.base import connection_options_for_engine


class TestSentryGuard:
    def test_sentry_not_active_in_local_environment(self):
        """local 환경에서 Sentry가 비활성화되어야 한다."""
        assert settings.SENTRY_ENVIRONMENT == "local"
        client = sentry_sdk.get_client()
        assert not client.is_active()

    def test_sentry_dsn_stripped(self):
        """SENTRY_DSN에 trailing whitespace가 제거되어야 한다."""
        assert settings.SENTRY_DSN == settings.SENTRY_DSN.strip()

    def test_sentry_environment_stripped(self):
        """SENTRY_ENVIRONMENT에 trailing whitespace가 제거되어야 한다."""
        assert (
            settings.SENTRY_ENVIRONMENT == settings.SENTRY_ENVIRONMENT.strip()
        )

    def test_capture_exception_returns_none_in_local(self):
        """local 환경에서 capture_exception이 None을 반환해야 한다."""
        try:
            raise ValueError("test error")
        except Exception as e:
            result = sentry_sdk.capture_exception(e)
        assert result is None

    def test_disallowed_host_logger_is_ignored_by_sentry(self):
        """스캐너 Host 헤더(DisallowedHost) 로그는 Sentry 로 가지 않는다.

        `_IGNORED_LOGGERS` 는 비공개 집합이지만 ignore_logger 의 유일한
        관측점이라 그대로 단언한다 (설정 동작을 보는 이 클래스에 둔다).
        """
        assert (
            "django.security.DisallowedHost" in sentry_logging._IGNORED_LOGGERS
        )


class TestConnectionOptions:
    @pytest.mark.parametrize(
        "engine",
        ["django.db.backends.postgresql", "timescale.db.backends.postgresql"],
    )
    def test_connection_options_applied_for_postgres_engines(self, engine):
        """postgresql 계열 엔진에 connect_timeout·keepalives가 적용되어야 한다."""
        options = connection_options_for_engine(engine)
        assert options["connect_timeout"] == 10
        assert options["keepalives"] == 1
        assert "options" not in options


class TestLoggingConfig:
    def test_base_logging_has_consumer_logger(self):
        """base.py LOGGING에 consumer 로거가 존재해야 한다."""
        assert "consumer" in settings.LOGGING["loggers"]

    def test_consumer_logger_has_console_handler(self):
        """consumer 로거에 콘솔 핸들러가 포함되어야 한다."""
        handlers = settings.LOGGING["loggers"]["consumer"]["handlers"]
        assert "consumer_console" in handlers

    def test_file_handlers_use_gzip_handler(self):
        """파일 핸들러가 GzipTimedRotatingFileHandler를 사용해야 한다."""
        for name, handler in settings.LOGGING["handlers"].items():
            if name.endswith("_file"):
                assert (
                    handler["class"]
                    == "backoffice.logging_handlers.GzipTimedRotatingFileHandler"
                )

    def test_file_handlers_use_utc(self):
        """파일 핸들러가 utc=True로 설정되어야 한다."""
        for name, handler in settings.LOGGING["handlers"].items():
            if name.endswith("_file"):
                assert handler.get("utc") is True
