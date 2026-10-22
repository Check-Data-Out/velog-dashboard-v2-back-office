#!/bin/bash

# 운영계에서만 사용할 script
# 실행 중인 gunicorn 마스터에 TERM(graceful)을 보내고 끝날 때까지 기다린다.
# pkill -f 처럼 명령줄 문자열로 고르면 명령줄에 "gunicorn" 이 들어간 SSH 세션까지 죽으므로 pid 로만 고른다.
set -euo pipefail

readonly PID_FILE=./gunicorn.pid
readonly APP='backoffice.wsgi:application'

pid=""
if [[ -f "$PID_FILE" ]]; then
    pid=$(cat "$PID_FILE")
    # pid 파일이 오래돼 다른 프로세스를 가리키면 쓰지 않는다
    if ! ps -p "$pid" -o args= 2>/dev/null | grep -qF "$APP"; then
        pid=""
    fi
fi
if [[ -z "$pid" ]]; then
    # pid 파일 없이 떠 있던 gunicorn: 가장 오래된 프로세스가 마스터다
    pid=$(pgrep -o -f "gunicorn .*${APP}" || true)
fi
if [[ -z "$pid" ]]; then
    echo "실행 중인 gunicorn 없음"
    exit 0
fi

kill -TERM "$pid"
for _ in $(seq 1 35); do
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "gunicorn 종료 (pid ${pid})"
        exit 0
    fi
    sleep 1
done

echo "35초 안에 끝나지 않아 강제 종료 (pid ${pid})" >&2
pkill -KILL -P "$pid" || true
kill -KILL "$pid" || true
