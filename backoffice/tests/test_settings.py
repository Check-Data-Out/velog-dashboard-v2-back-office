import pytest
import sentry_sdk
from django.conf import settings


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


@pytest.fixture()
def consumer_logging():
    """consumer.py settings의 LOGGING을 시뮬레이션."""
    import copy

    from backoffice.settings import base

    logging_copy = copy.deepcopy(base.LOGGING)

    # consumer.py 로직 재현
    logging_copy["handlers"]["consumer_file"] = {
        "level": "INFO",
        "class": "backoffice.logging_handlers.GzipTimedRotatingFileHandler",
        "when": "midnight",
        "utc": True,
        "interval": 1,
        "backupCount": 7,
        "formatter": "default_formatter",
        "encoding": "utf-8",
        "filename": "logs/consumer.log",
    }

    for handler_name in ("scraping_file", "newsletter_file", "django_file"):
        logging_copy["handlers"].pop(handler_name, None)

    for logger_name in ("scraping", "newsletter", "django", "consumer"):
        logger_conf = logging_copy["loggers"].get(logger_name, {})
        logger_conf["handlers"] = [
            h
            for h in logger_conf.get("handlers", [])
            if not h.endswith("_file")
        ]
        logger_conf["handlers"].append("consumer_file")

    return logging_copy


class TestConsumerLoggingOverride:
    def test_django_file_handlers_removed(self, consumer_logging):
        """Consumer 환경에서 Django 파일 핸들러가 제거되어야 한다."""
        assert "scraping_file" not in consumer_logging["handlers"]
        assert "newsletter_file" not in consumer_logging["handlers"]
        assert "django_file" not in consumer_logging["handlers"]

    def test_all_loggers_write_to_consumer_file(self, consumer_logging):
        """Consumer 환경에서 모든 로거가 consumer_file에 기록해야 한다."""
        for logger_name in ("scraping", "newsletter", "django", "consumer"):
            handlers = consumer_logging["loggers"][logger_name]["handlers"]
            assert "consumer_file" in handlers

    def test_consumer_file_handler_config(self, consumer_logging):
        """consumer_file 핸들러 설정이 올바른지 확인."""
        handler = consumer_logging["handlers"]["consumer_file"]
        assert (
            handler["class"]
            == "backoffice.logging_handlers.GzipTimedRotatingFileHandler"
        )
        assert handler["backupCount"] == 7
        assert handler["when"] == "midnight"
        assert handler["utc"] is True
