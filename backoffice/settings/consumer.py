"""Consumer 전용 settings.

Docker container에서 consumer 실행 시 사용.
- debug_toolbar, django_extensions 제외 (dev 의존성)
- DB 연결은 환경변수로 설정 (local/prod 모두 지원)
"""

import os

from .base import *  # noqa: F401, F403

DEBUG = False

# dev 의존성 앱 제거
INSTALLED_APPS = [  # noqa: F405
    app
    for app in INSTALLED_APPS  # noqa: F405
    if app not in ("debug_toolbar", "django_extensions")
]

# dev 의존성 미들웨어 제거
MIDDLEWARE = [  # noqa: F405
    mw
    for mw in MIDDLEWARE  # noqa: F405
    if "debug_toolbar" not in mw
]

INTERNAL_IPS = []

# Consumer 전용 로그 디렉토리 — Django의 logs/와 완전 분리하여 권한 충돌 방지
CONSUMER_LOG_DIR = os.path.join(BASE_DIR, "consumer-logs")  # noqa: F405
os.makedirs(CONSUMER_LOG_DIR, exist_ok=True)

# Consumer 전용 파일 핸들러 — 모든 로그를 consumer-logs/consumer.log에 기록
# Django 프로세스(ubuntu)와 Consumer(Docker root)의 로그 디렉토리를 분리하여
# 바인드 마운트 권한 충돌을 원천 차단
LOGGING["handlers"]["consumer_file"] = {  # noqa: F405
    "level": "INFO",
    "class": "backoffice.logging_handlers.GzipTimedRotatingFileHandler",
    "when": "midnight",
    "utc": True,
    "interval": 1,
    "backupCount": 7,
    "formatter": "default_formatter",
    "encoding": "utf-8",
    "filename": os.path.join(CONSUMER_LOG_DIR, "consumer.log"),
}

# base.py의 Django 전용 파일 핸들러 제거
for handler_name in ("scraping_file", "newsletter_file", "django_file"):
    LOGGING["handlers"].pop(handler_name, None)  # noqa: F405

# 모든 로거를 consumer_console + consumer_file로 통합
for logger_name in ("scraping", "newsletter", "django", "consumer"):
    logger_conf = LOGGING["loggers"].setdefault(  # noqa: F405
        logger_name,
        {
            "level": "INFO",
            "propagate": False,
        },
    )
    logger_conf["handlers"] = [
        h for h in logger_conf.get("handlers", []) if not h.endswith("_file")
    ]
    logger_conf["handlers"].append("consumer_file")
