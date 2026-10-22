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

if ! curl -fsS -o /dev/null -H "Host: ${HEALTH_HOST}" \
    --retry 10 --retry-delay 2 --retry-all-errors "$HEALTH_URL"; then
    echo "헬스체크 실패: ${HEALTH_URL}" >&2
    tail -n 20 ./gunicorn-error.log >&2 || true
    exit 1
fi

echo "gunicorn 기동 완료 (pid $(cat "$PID_FILE"))"
