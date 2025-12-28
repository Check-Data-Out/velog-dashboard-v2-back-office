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
