"""Phase 7 — /healthz 핸들러 단위 테스트 (BaseHTTPRequestHandler 로직만 검증)."""

import json
import time
from unittest.mock import MagicMock

from consumer.healthz import _build_handler


class _FakeRequest:
    """BaseHTTPRequestHandler 가 필요로 하는 최소 request 모의체."""

    def __init__(self, path: str = "/healthz"):
        self.path = path
        self.response_code = None
        self.headers_sent = {}
        self.body = b""

    def send_response(self, code):
        self.response_code = code

    def send_header(self, key, value):
        self.headers_sent[key] = value

    def end_headers(self):
        pass

    @property
    def wfile(self):
        class _W:
            def __init__(self, outer):
                self.outer = outer

            def write(self, b):
                self.outer.body += b

        return _W(self)


def _call_handler(handler_cls, path="/healthz"):
    """BaseHTTPRequestHandler 를 실제 socket 없이 do_GET 만 호출."""
    fake = _FakeRequest(path)
    # handler 인스턴스화 우회: 필요한 메서드만 bind
    handler = handler_cls.__new__(handler_cls)
    handler.path = fake.path
    handler.wfile = fake.wfile
    handler.send_response = fake.send_response
    handler.send_header = fake.send_header
    handler.end_headers = fake.end_headers
    handler_cls.do_GET(handler)
    return fake


class TestHealthz:
    def test_returns_200_when_redis_ok_and_heartbeat_fresh(self):
        stats = {
            "last_heartbeat_at": time.time(),
            "processed": 10,
            "succeeded": 9,
            "failed": 1,
            "last_message_at": time.time(),
        }
        redis_client = MagicMock()
        redis_client.client = MagicMock()
        redis_client.client.ping = MagicMock(return_value=True)

        Handler = _build_handler(lambda: stats, redis_client, 60)
        fake = _call_handler(Handler)
        assert fake.response_code == 200
        payload = json.loads(fake.body)
        assert payload["status"] == "ok"
        assert payload["redis"] is True

    def test_returns_503_when_redis_ping_fails(self):
        stats = {"last_heartbeat_at": time.time()}
        redis_client = MagicMock()
        redis_client.client = MagicMock()
        redis_client.client.ping.side_effect = Exception("conn")

        Handler = _build_handler(lambda: stats, redis_client, 60)
        fake = _call_handler(Handler)
        assert fake.response_code == 503
        payload = json.loads(fake.body)
        assert payload["redis"] is False

    def test_returns_503_when_heartbeat_stale(self):
        stats = {"last_heartbeat_at": time.time() - 9999}
        redis_client = MagicMock()
        redis_client.client = MagicMock()
        redis_client.client.ping = MagicMock(return_value=True)

        Handler = _build_handler(lambda: stats, redis_client, 60)
        fake = _call_handler(Handler)
        assert fake.response_code == 503

    def test_returns_200_during_idle_period_if_heartbeat_fresh(self):
        # 메시지가 없어도 heartbeat 만 최신이면 healthy
        stats = {
            "last_heartbeat_at": time.time() - 2,
            "last_message_at": None,
        }
        redis_client = MagicMock()
        redis_client.client = MagicMock()
        redis_client.client.ping = MagicMock(return_value=True)

        Handler = _build_handler(lambda: stats, redis_client, 60)
        fake = _call_handler(Handler)
        assert fake.response_code == 200
        payload = json.loads(fake.body)
        assert payload["status"] == "ok"

    def test_non_healthz_path_returns_404(self):
        redis_client = MagicMock()
        Handler = _build_handler(
            lambda: {"last_heartbeat_at": time.time()}, redis_client, 60
        )
        fake = _call_handler(Handler, path="/other")
        assert fake.response_code == 404
