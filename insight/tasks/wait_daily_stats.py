"""
월요일 사용자 분석 전에, 그날 일일 통계 배치(20개 세트)가 모두 성공했는지
GitHub Actions run 목록으로 확인하고 다 모일 때까지 기다린다.

- Django 없이 표준 라이브러리만 쓴다.
- 공개 레포라 토큰 없이 읽힌다. GITHUB_TOKEN 환경변수가 있으면 붙인다.
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

GITHUB_REPO = "Check-Data-Out/velog-dashboard-v2-back-office"
RUNS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs"
KST = ZoneInfo("Asia/Seoul")
REQUEST_TIMEOUT_SEC = 30

# .github/workflows/run-daily-aggre-set*.yaml 의 name
DAILY_STATS_WORKFLOW = "Daily Stats Batch (set{})"
DAILY_STATS_SET_COUNT = 20

# 아직 끝나지 않은 run 의 status
ACTIVE_RUN_STATUSES = ("queued", "in_progress", "waiting", "pending")

# 5분 간격으로 최대 90분 (조회 실패가 없으면 최대 19회, 비인증 한도 시간당 60회 안)
WAIT_TIMEOUT_SEC = 90 * 60
WAIT_INTERVAL_SEC = 5 * 60
# 조회가 실패하면 이만큼 뒤 다시 본다. 이만큼 잇달아 실패하면 더 기다리지 않는다
FETCH_RETRY_SEC = 30
MAX_FETCH_ERRORS = 3


def _get_json(url: str) -> dict:
    """GitHub API GET 응답 JSON. GITHUB_TOKEN 이 있으면 인증 헤더를 붙인다"""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(
        request, timeout=REQUEST_TIMEOUT_SEC
    ) as response:
        return json.loads(response.read())


def fetch_today_success_runs(now: datetime) -> list[dict]:
    """now 가 속한 날(KST) 00:00 이후 성공한 run 을 모은다.

    run 은 최신순으로 온다. 일일 통계 세트를 다 찾으면 남은 쪽은 읽지 않는다
    (보통 첫 쪽에서 끝난다).
    """
    today_start = now.astimezone(KST).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    runs: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "status": "success",
                "created": f">={today_start.isoformat()}",
                "per_page": 100,
                "page": page,
            }
        )
        data = _get_json(f"{RUNS_URL}?{query}")
        page_runs = data.get("workflow_runs", [])
        runs.extend(page_runs)
        if (
            not page_runs
            or not missing_sets(runs)
            or len(runs) >= data.get("total_count", 0)
        ):
            return runs
        page += 1


def fetch_recent_runs() -> list[dict]:
    """상태와 관계없이 최근 run 100개. 진행 중인 run 이 있는지 볼 때 쓴다"""
    return _get_json(f"{RUNS_URL}?per_page=100").get("workflow_runs", [])


def missing_sets(runs: list[dict]) -> list[int]:
    """run 목록에 없는 일일 통계 세트 번호(오름차순)

    Args:
        runs: 오늘 성공한 run 목록 (GitHub API 의 workflow_runs)
    """
    names = {run.get("name") for run in runs}
    return [
        set_no
        for set_no in range(1, DAILY_STATS_SET_COUNT + 1)
        if DAILY_STATS_WORKFLOW.format(set_no) not in names
    ]


def has_active_run(runs: list[dict], workflow_name: str) -> bool:
    """workflow_name 의 run 중 아직 끝나지 않은(대기·실행 중) 것이 있는지"""
    return any(
        run.get("name") == workflow_name
        and run.get("status") in ACTIVE_RUN_STATUSES
        for run in runs
    )


def wait_for_daily_stats(
    now: datetime,
    fetch: Callable[[datetime], list[dict]],
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    logger: logging.Logger,
    timeout_sec: int = WAIT_TIMEOUT_SEC,
    interval_sec: int = WAIT_INTERVAL_SEC,
) -> list[int]:
    """오늘 일일 통계 세트가 모두 성공할 때까지 기다린다.

    다 모였으면 바로 끝난다. 아니면 interval_sec 마다(조회가 실패했으면
    FETCH_RETRY_SEC 뒤) 다시 보고, timeout_sec 이 지나거나 조회가 잇달아
    실패하면 빠진 세트를 경고로 남기고 끝낸다.
    통계가 덜 모여도 분석은 진행해야 하므로 예외를 내지 않는다.

    Args:
        now: 기준 시각. 이날 00:00(KST) 이후 run 을 본다.
        fetch: now 를 받아 성공 run 목록을 돌려주는 함수
        sleep: 초 단위로 기다리는 함수
        clock: 지금 시각을 초로 돌려주는 단조 시계
        logger: 진행·경고 로그
        timeout_sec: 최대 대기 시간(초)
        interval_sec: 조회 간격(초)

    Returns:
        끝까지 성공 run 이 없던 세트 번호. 모두 끝났으면 빈 리스트.
    """
    deadline = clock() + timeout_sec
    # 한 번도 조회하지 못하면 모든 세트를 빠진 것으로 본다
    missing = list(range(1, DAILY_STATS_SET_COUNT + 1))
    errors = 0
    while True:
        try:
            runs = fetch(now)
        except Exception as e:  # 조회 실패가 분석을 막지 않게 모두 삼킨다
            errors += 1
            logger.warning("Failed to fetch daily stats runs: %s", e)
        else:
            errors = 0
            missing = missing_sets(runs)
            if not missing:
                logger.info("All daily stats sets completed")
                return []
            logger.info("Waiting for daily stats sets: %s", missing)

        wait_sec = FETCH_RETRY_SEC if errors else interval_sec
        if errors >= MAX_FETCH_ERRORS or clock() + wait_sec > deadline:
            break
        sleep(wait_sec)

    logger.warning("Proceeding without daily stats sets: %s", missing)
    return missing
