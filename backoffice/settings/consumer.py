"""Consumer 전용 settings.

Docker container에서 consumer 실행 시 사용.
- debug_toolbar, django_extensions 제외 (dev 의존성)
- DB 연결은 환경변수로 설정 (local/prod 모두 지원)
"""

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

# Consumer 전용 파일 핸들러 — 모든 로그를 consumer.log에 기록
# scraping.log 등 Django 로그 파일은 권한 충돌 방지를 위해 제거하고,
# 해당 로거들의 파일 출력을 consumer_file로 통합
LOGGING["handlers"]["consumer_file"] = {  # noqa: F405
    "level": "INFO",
    "class": "backoffice.logging_handlers.GzipTimedRotatingFileHandler",
    "when": "midnight",
    "utc": True,
    "interval": 1,
    "backupCount": 7,
    "formatter": "default_formatter",
    "encoding": "utf-8",
    "filename": os.path.join(BASE_DIR, "logs", "consumer.log"),  # noqa: F405
}

for handler_name in ("scraping_file", "newsletter_file", "django_file"):
    LOGGING["handlers"].pop(handler_name, None)  # noqa: F405

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
