#!/bin/bash

# 운영 BO 서버에서 주간 배치(공통 분석·사용자 분석·뉴스레터 발송)를 실행하는 script
# 사용법: ./run-weekly.sh <trend|user-analysis|newsletter>
#
# crontab 예시 (서버 시간대 UTC 기준, 월요일 07:00·09:30 KST)
#   0 22 * * 0  <레포 폴더>/run-weekly.sh trend && <레포 폴더>/run-weekly.sh user-analysis
#   30 0 * * 1  <레포 폴더>/run-weekly.sh newsletter
# 두 분석은 반드시 한 줄로 잇는다. 사용자 분석은 공통 분석 결과 행이 있어야 하고, 같은 결과 파일을 쓴다
#
# 수동 실행도 반드시 이 스크립트로 한다. 파이썬 스크립트를 직접 부르면 잠금·GitHub run 겹침 확인을 거치지 않는다
# 로그는 ~/weekly-batch/logs, 마지막 성공 시각 지표는 ~/weekly-batch/metrics(node_exporter textfile 폴더)에 남는다
# Slack 웹훅은 .env.prod 의 SLACK_WEBHOOK_URL 을 쓴다. 없으면 알림만 생략한다
set -euo pipefail
# 로그·잠금·결과·지표 파일을 본인만 읽게 한다 (node_exporter 는 같은 사용자로 돌아야 지표를 읽는다)
umask 077

cd "$(dirname "$(readlink -f "$0")")"

readonly USAGE="사용법: $0 <trend|user-analysis|newsletter>"
readonly BATCH_HOME="$HOME/weekly-batch"
readonly LOG_DIR="$BATCH_HOME/logs"
readonly METRICS_DIR="$BATCH_HOME/metrics"
readonly PYTHON=./.venv/bin/python
readonly METRIC=vd_weekly_batch_last_success_timestamp_seconds

JOB="${1:-}"
case "$JOB" in
    trend)
        SCRIPT=weekly_trend_analysis
        WORKFLOW="Weekly Analysis Batch"
        TITLE="*Weekly Analysis Batch — 공통 분석*"
        RESULT_FILE=weekly_analysis_result.txt
        LIMIT=10m
        ;;
    user-analysis)
        SCRIPT=weekly_user_trend_analysis
        WORKFLOW="Weekly Analysis Batch"
        TITLE="*Weekly Analysis Batch — 사용자 분석*"
        RESULT_FILE=weekly_analysis_result.txt
        # 월요일 통계 대기 90분 + 분석 40분 + 여유
        LIMIT=135m
        ;;
    newsletter)
        SCRIPT=weekly_newsletter_batch
        WORKFLOW="Weekly Newsletter Batch"
        TITLE="*Weekly Newsletter Batch*"
        RESULT_FILE=newsletter_batch_result.txt
        LIMIT=48m
        ;;
    *)
        echo "$USAGE" >&2
        exit 2
        ;;
esac
readonly JOB SCRIPT WORKFLOW TITLE RESULT_FILE LIMIT
# 파이썬이 할 일 없이 끝났을 때 현재 폴더에 남기는 표시 파일
readonly SKIP_MARKER="$SCRIPT.skipped"

mkdir -p "$LOG_DIR" "$METRICS_DIR"
LOG="$LOG_DIR/$JOB-$(TZ=Asia/Seoul date +%Y%m%d).log"
readonly LOG
exec >>"$LOG" 2>&1

# 줄 앞에 KST 시각을 붙여 로그에 남긴다
log() {
    echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 8주 지난 로그는 지운다
find "$LOG_DIR" -name '*.log' -mtime +56 -delete

# 같은 작업이 이미 돌고 있으면 파이썬·DB·Slack 을 건드리지 않고 끝낸다
# (잠금은 파이썬까지 물려받아 끝날 때까지 유지된다. run.sh 도 이 잠금을 보고 배포를 멈춘다)
exec 9>"$BATCH_HOME/$JOB.lock"
if ! flock -n 9; then
    log "이미 실행 중, 건너뜀"
    exit 0
fi

# 같은 워크플로의 GitHub run 이 돌고 있으면 그쪽에 맡긴다
# 조회가 실패하면 진행한다 (GitHub 쪽 판정은 DB 를 보고 물러난다: 분석은 이번 주 WeeklyTrend 행, 발송은 시작 표시)
set +e
"$PYTHON" insight/tasks/wait_daily_stats.py "$WORKFLOW"
active=$?
set -e
case $active in
    0) ;;
    3)
        log "GitHub run 진행 중, 건너뜀"
        exit 0
        ;;
    *) log "GitHub 조회 실패, 진행 (exit $active)" ;;
esac

# 지난 실행이 남긴 결과 파일과 건너뜀 표시를 지운다 (파이썬은 표시 파일을 지우지 않는다)
rm -f "$RESULT_FILE" "$SKIP_MARKER"

# 환경변수가 .env.prod 보다 우선한다 (django-environ read_env 는 이미 있는 값을 덮어쓰지 않는다)
# 배치는 Supabase pooler 트랜잭션 모드(6543)로 붙는다
export DJANGO_SETTINGS_MODULE=backoffice.settings.prod
export POSTGRES_PORT=6543
export MALLOC_ARENA_MAX=2

# 메모리가 모자라면 커널이 gunicorn·consumer 보다 배치를 먼저 죽이게 하고(choom), CPU 도 양보한다(nice)
log "$SCRIPT 시작 (제한 $LIMIT)"
set +e
timeout -k 60 "$LIMIT" nice -n 10 choom -n 1000 -- "$PYTHON" "insight/tasks/$SCRIPT.py"
rc=$?
set -e
log "$SCRIPT 종료 (exit $rc)"

# 성공(건너뜀 포함)이면 마지막 성공 시각 지표를 갱신한다. 같은 폴더에 쓴 뒤 mv 해 반쯤 쓴 파일을 읽지 않게 한다
if [[ $rc -eq 0 ]]; then
    prom="$METRICS_DIR/weekly_batch_$JOB.prom"
    {
        echo "# HELP $METRIC Unix time of the last successful weekly batch run."
        echo "# TYPE $METRIC gauge"
        echo "$METRIC{job=\"$JOB\"} $(date +%s)"
    } >"$prom.$$"
    mv "$prom.$$" "$prom"
fi

# 표시 파일이 있어도 실패로 끝났으면 알린다
if [[ $rc -eq 0 && -e "$SKIP_MARKER" ]]; then
    log "할 일 없이 끝나 Slack 을 보내지 않음"
    exit "$rc"
fi

webhook="$(sed -n 's/^SLACK_WEBHOOK_URL=//p' .env.prod 2>/dev/null | tail -n 1 | tr -d "\"'" || true)"
if [[ -z "$webhook" ]]; then
    log "Slack 웹훅 없음, 알림 생략"
    exit "$rc"
fi

if [[ $rc -eq 0 ]]; then
    status="✅ *Status:* success"
elif [[ $rc -eq 124 ]]; then
    status="❌ *Status:* 시간 제한 초과"
else
    status="❌ *Status:* failure (exit $rc)"
fi
if [[ -s "$RESULT_FILE" ]]; then
    result="$(cat "$RESULT_FILE")"
else
    result="결과 파일 없음"
fi

payload_file="$(mktemp)"
trap 'rm -f "$payload_file"' EXIT

# Slack 텍스트에서 & < > 는 이스케이프해야 그대로 보인다. JSON 은 파이썬 json.dumps 로 만든다
{
    printf '%s\n\n' "$TITLE"
    printf '%s\n' "$status"
    printf '📅 *Timestamp (KST):* %s\n' "$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S')"
    printf '🖥 *실행 위치:* BO 서버\n'
    # 코드 블록 백틱은 문자 그대로 쓴다
    # shellcheck disable=SC2016
    printf '📝 *Result:*\n```\n%s\n```\n' "$result"
    printf '📄 *Log:* %s\n' "$LOG"
} | "$PYTHON" -c '
import json
import sys

text = sys.stdin.read()
text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
print(json.dumps({"text": text}))
' >"$payload_file"

# 웹훅 주소는 표준입력 설정(-K -)으로 넘겨 명령줄·로그에 나오지 않게 한다. 전송 실패는 종료 코드를 바꾸지 않는다
if printf 'url = "%s"\n' "$webhook" \
    | curl -fsS --max-time 15 -H 'Content-Type: application/json' --data @"$payload_file" -K - >/dev/null; then
    log "Slack 전송 완료"
else
    log "Slack 전송 실패"
fi

exit "$rc"
