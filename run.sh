#!/bin/bash

# 운영계에서만 사용할 script
# chmod +x run.sh
set -euo pipefail

readonly PID_FILE=./gunicorn.pid
readonly HEALTH_URL=http://127.0.0.1:8000/admin/login/
# 운영 ALLOWED_HOSTS 에 127.0.0.1 이 없어 Host 를 지정한다
readonly HEALTH_HOST=admin-vd2.kro.kr

# 설치·정적 파일·마이그레이션은 기존 gunicorn 을 띄워 둔 채로 먼저 한다 (실패하면 기존 서비스 유지)
source ./.venv/bin/activate
pip install -r requirements.txt

export DJANGO_SETTINGS_MODULE=backoffice.settings.prod
python manage.py collectstatic --no-input
python manage.py migrate

bash ./run-kill.sh

gunicorn --workers 2 --bind 0.0.0.0:8000 --log-level=info \
    --log-file=./gunicorn.log --access-logfile=./gunicorn-access.log \
    --error-logfile=./gunicorn-error.log --max-requests=1200 \
    --max-requests-jitter=100 --pid "$PID_FILE" \
    backoffice.wsgi:application --daemon

# 응답한 것이 새로 띄운 마스터인지도 본다 (남은 옛 워커가 대신 응답하는 경우를 거른다)
if ! curl -fsS -o /dev/null -H "Host: ${HEALTH_HOST}" --connect-timeout 2 --max-time 5 \
    --retry 10 --retry-delay 2 --retry-all-errors "$HEALTH_URL" \
    || ! kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
    echo "헬스체크 실패: ${HEALTH_URL}" >&2
    tail -n 20 ./gunicorn-error.log >&2 || true
    echo "기존 gunicorn 은 이미 종료됐습니다. 직전 커밋($(git rev-parse --short 'HEAD@{1}' 2>/dev/null || echo '?'))으로 되돌린 뒤 ./run.sh 를 다시 실행하세요." >&2
    exit 1
fi

echo "gunicorn 기동 완료 (pid $(cat "$PID_FILE"))"
