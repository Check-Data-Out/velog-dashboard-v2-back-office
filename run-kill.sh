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
        # 남겨 두면 그 pid 를 다른 프로세스가 쓰는 동안 새 gunicorn 이 "Already running" 으로 뜨지 않는다
        rm -f "$PID_FILE"
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

# 검사 직후 스스로 끝났을 수 있으므로 실패해도 넘어가고, 아래에서 종료 여부를 본다
kill -TERM "$pid" 2>/dev/null || true
for _ in $(seq 1 35); do
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "gunicorn 종료 (pid ${pid})"
        exit 0
    fi
    sleep 1
done

# 마스터를 먼저 죽여야 워커를 다시 띄우지 않는다. 남은 워커가 :8000 을 잡고 있으면 새 gunicorn 이 뜨지 못한다
echo "35초 안에 끝나지 않아 강제 종료 (pid ${pid})" >&2
children=$(pgrep -P "$pid" || true)
kill -KILL "$pid" 2>/dev/null || true
if [[ -n "$children" ]]; then
    kill -KILL $children 2>/dev/null || true
fi
# kill -0 에 pid 를 여러 개 주면 하나만 없어도 실패하므로 하나씩 본다
for _ in $(seq 1 5); do
    alive=""
    for p in $pid $children; do
        kill -0 "$p" 2>/dev/null && alive="$alive $p"
    done
    if [[ -z "$alive" ]]; then
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done
echo "강제 종료 후에도 프로세스가 남아 있음 (pid ${pid} ${children})" >&2
exit 1
