import http.server
import json
import logging
import socketserver
import threading
import time
from collections.abc import Callable

from consumer.config import ConsumerConfig
from modules.redis.client import RedisQueueClient

logger = logging.getLogger("consumer")


def _build_handler(
    stats_provider: Callable[[], dict],
    redis_client: RedisQueueClient,
    stale_threshold_sec: int,
):
    """Handler class 를 stats_provider 에 클로저로 묶어 반환."""

    class _HealthzHandler(http.server.BaseHTTPRequestHandler):
        # access log 억제
        def log_message(self, format, *args):  # noqa: A002
            return

        def do_GET(self):
            if self.path != "/healthz":
                self.send_response(404)
                self.end_headers()
                return

            stats = stats_provider()
            now = time.time()
            last_heartbeat = stats.get("last_heartbeat_at") or stats.get(
                "start_time", now
            )
            age = now - float(last_heartbeat)

            redis_ok = True
            try:
                if redis_client.client is None:
                    redis_ok = False
                else:
                    redis_client.client.ping()
            except Exception:
                redis_ok = False

            healthy = redis_ok and age < stale_threshold_sec
            payload = {
                "status": "ok" if healthy else "stale",
                "redis": redis_ok,
                "heartbeat_age_sec": round(age, 2),
                "processed": stats.get("processed", 0),
                "succeeded": stats.get("succeeded", 0),
                "failed": stats.get("failed", 0),
                "last_message_at": stats.get("last_message_at"),
            }
            self.send_response(200 if healthy else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

    return _HealthzHandler


class _ReuseAddrTCPServer(socketserver.TCPServer):
    """`allow_reuse_address=True` 를 server_bind() 이전에 적용하기 위한 서브클래스.

    Python stdlib 의 TCPServer.__init__ 은 즉시 server_bind() 를 호출하고
    이 시점에 setsockopt(SO_REUSEADDR) 을 **클래스 속성** 을 참조해 설정한다.
    인스턴스 할당은 이미 바인딩된 소켓에 영향이 없기 때문에, 클래스 속성으로
    선언해야 재시작 시 'Address already in use' 를 실제로 피할 수 있다.
    """

    allow_reuse_address = True


def start_healthz_server(
    stats_provider: Callable[[], dict],
    redis_client: RedisQueueClient,
    config: type[ConsumerConfig] | None = None,
) -> threading.Thread:
    """healthz 서버를 daemon thread 로 기동. 호출자는 shutdown 시 프로세스 종료로 정리."""
    cfg = config or ConsumerConfig
    handler_cls = _build_handler(
        stats_provider, redis_client, cfg.HEALTHZ_STALE_THRESHOLD_SEC
    )

    server = _ReuseAddrTCPServer(("127.0.0.1", cfg.HEALTHZ_PORT), handler_cls)

    def _serve():
        logger.info(
            f"/healthz listening on 127.0.0.1:{cfg.HEALTHZ_PORT} (stale={cfg.HEALTHZ_STALE_THRESHOLD_SEC}s)"
        )
        try:
            server.serve_forever(poll_interval=1.0)
        except Exception as e:
            logger.error(f"healthz server crashed: {e}")

    thread = threading.Thread(target=_serve, name="HealthzServer", daemon=True)
    thread.start()
    return thread
