import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKER_COMPOSE_PATH = REPO_ROOT / "docker-compose.yaml"


def test_stats_refresh_consumer_mounts_consumer_logs_for_both_paths():
    """구이미지와 신이미지 모두 같은 host 로그 디렉토리를 사용해야 한다."""
    compose_text = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")
    service_match = re.search(
        r"stats-refresh-consumer:\n(?P<body>(?: {2,}.*\n)+)",
        compose_text,
    )

    assert service_match is not None

    service_body = service_match.group("body")

    assert "- ./consumer-logs:/app/consumer-logs" in service_body
    assert "- ./consumer-logs:/app/logs" in service_body
