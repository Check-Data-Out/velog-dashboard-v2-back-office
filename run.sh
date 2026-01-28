#!/bin/bash

# 운영계에서만 사용할 script
# chmod +x run.sh
set -e  # 에러 발생 시 스크립트 중지
source ./run-kill.sh

# 가상환경 액티베이션 & 라이브러리 설치
source ./.venv/bin/activate
pip install -r requirements.txt

export DJANGO_SETTINGS_MODULE=backoffice.settings.prod
python manage.py collectstatic --no-input
python manage.py migrate

sleep 1
gunicorn --workers 2 --bind 0.0.0.0:8000 --log-level=info \
    --log-file=./gunicorn.log --access-logfile=./gunicorn-access.log \
    --error-logfile=./gunicorn-error.log --max-requests=1200 \
    --max-requests-jitter=100 backoffice.wsgi:application --daemon

sleep 1

ps -ef | grep gunicorn | grep -v grep
sleep 1
tail ./gunicorn-access.log
