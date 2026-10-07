import ssl
from unittest.mock import Mock, patch

import aiohttp
import pytest
from django.db import OperationalError

from scraping.apis import VelogFetchError
from scraping.main import TokenUpdateError
from scraping.reporting import (
    SOURCE_VELOG_API,
    VelogApiError,
    capture_scraper_failure,
    cause_for,
)


def _chained(exc: Exception, cause: BaseException) -> Exception:
    try:
        raise cause
    except BaseException as e:
        try:
            raise exc from e
        except Exception as chained:
            return chained


def _fetch_error_from(cause: BaseException) -> VelogFetchError:
    err = _chained(VelogFetchError("page failed"), cause)
    assert isinstance(err, VelogFetchError)
    return err


def test_velog_fetch_error_is_marked_as_velog_api_error():
    assert issubclass(VelogFetchError, VelogApiError)


@pytest.mark.parametrize(
    "exc, expected",
    [
        (
            aiohttp.ClientConnectorCertificateError(
                Mock(), ssl.SSLCertVerificationError("hostname mismatch")
            ),
            "ssl",
        ),
        (aiohttp.ServerTimeoutError("slow"), "timeout"),
        (TimeoutError("slow"), "timeout"),
        (aiohttp.ClientConnectorDNSError(Mock(), OSError("dns")), "dns"),
        (aiohttp.ClientConnectorError(Mock(), OSError("refused")), "connect"),
        (aiohttp.ClientResponseError(Mock(), (), status=502), "http"),
        (aiohttp.ClientPayloadError("truncated"), "payload"),
        (aiohttp.ServerDisconnectedError(), "connection"),
        (aiohttp.ClientOSError(), "connection"),
        (KeyError("data"), "malformed"),
        (Exception("x"), None),
        (OperationalError("db"), None),
    ],
    ids=[
        "ssl",
        "server-timeout",
        "builtin-timeout",
        "dns",
        "connect",
        "http",
        "payload",
        "server-disconnected",
        "client-os",
        "malformed",
        "generic",
        "db",
    ],
)
def test_cause_for(exc, expected):
    assert cause_for(exc) == expected


class TestCaptureScraperFailure:
    @patch("sentry_sdk.capture_exception")
    def test_velog_api_known_cause_uses_fixed_fingerprint(self, mock_capture):
        exc = aiohttp.ClientConnectorCertificateError(
            Mock(), ssl.SSLCertVerificationError("hostname mismatch")
        )

        capture_scraper_failure(exc, source=SOURCE_VELOG_API, username="u1")

        mock_capture.assert_called_once_with(
            exc,
            fingerprint=["scraper", SOURCE_VELOG_API, "ssl"],
            tags={"scraper.cause": "ssl", "username": "u1"},
        )

    @patch("scraping.reporting.time.monotonic")
    @patch("sentry_sdk.capture_exception")
    def test_chained_velog_error_without_source_uses_cause_grouping(
        self, mock_capture, mock_monotonic
    ):
        """최종 지점(consumer/배치)은 source 없이 호출하지만 __cause__ 가
        velog 네트워크 예외면 같은 fingerprint·윈도로 묶인다."""
        mock_monotonic.return_value = 1000.0
        exc = _fetch_error_from(aiohttp.ServerDisconnectedError())

        capture_scraper_failure(exc, user_id=7)
        capture_scraper_failure(exc, user_id=7)  # 윈도 안 → 억제

        mock_capture.assert_called_once_with(
            exc,
            fingerprint=["scraper", SOURCE_VELOG_API, "connection"],
            tags={"user_id": "7", "scraper.cause": "connection"},
        )

    @patch("scraping.reporting.time.monotonic")
    @patch("sentry_sdk.capture_exception")
    def test_non_velog_error_with_network_like_cause_keeps_default_grouping(
        self, mock_capture, mock_monotonic
    ):
        """TokenUpdateError from KeyError(쿠키 키 누락)는 velog-api/malformed 로
        오분류돼 600s 억제되면 안 된다 — VelogApiError 가 아니면 체인 무시."""
        mock_monotonic.return_value = 1000.0
        exc = _chained(TokenUpdateError("tokens"), KeyError("access_token"))

        capture_scraper_failure(exc, user_id=7)
        capture_scraper_failure(exc, user_id=7)

        assert mock_capture.call_count == 2
        mock_capture.assert_called_with(exc, tags={"user_id": "7"})

    @patch("sentry_sdk.capture_exception")
    def test_without_source_uses_default_grouping_and_no_dedupe(
        self, mock_capture
    ):
        """source 없음 → fingerprint 없이 capture, 윈도 dedupe 도 없다.

        값이 None 인 태그는 생략된다.
        """
        exc = KeyError("data")

        capture_scraper_failure(exc, user_id=7, username=None)
        capture_scraper_failure(exc, user_id=7, username=None)

        assert mock_capture.call_count == 2
        mock_capture.assert_called_with(exc, tags={"user_id": "7"})

    @patch("scraping.reporting.time.monotonic")
    @patch("sentry_sdk.capture_exception")
    def test_same_cause_within_window_is_suppressed_and_counted(
        self, mock_capture, mock_monotonic
    ):
        exc = aiohttp.ServerTimeoutError("slow")

        mock_monotonic.return_value = 1000.0
        capture_scraper_failure(exc, source=SOURCE_VELOG_API)
        mock_monotonic.return_value = 1100.0
        capture_scraper_failure(exc, source=SOURCE_VELOG_API)
        mock_monotonic.return_value = 1200.0
        capture_scraper_failure(exc, source=SOURCE_VELOG_API)

        assert mock_capture.call_count == 1

        mock_monotonic.return_value = 1000.0 + 600.0
        capture_scraper_failure(exc, source=SOURCE_VELOG_API)

        assert mock_capture.call_count == 2
        kwargs = mock_capture.call_args.kwargs
        assert kwargs["tags"]["scraper.suppressed"] == "2"
        assert "suppressed_since" in kwargs["extras"]

    @patch("scraping.reporting.time.monotonic")
    @patch("sentry_sdk.capture_exception")
    def test_different_cause_within_window_is_still_sent(
        self, mock_capture, mock_monotonic
    ):
        mock_monotonic.return_value = 1000.0
        capture_scraper_failure(
            aiohttp.ServerTimeoutError("slow"), source=SOURCE_VELOG_API
        )
        capture_scraper_failure(
            aiohttp.ClientConnectorDNSError(Mock(), OSError("dns")),
            source=SOURCE_VELOG_API,
        )

        assert mock_capture.call_count == 2
