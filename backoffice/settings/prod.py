from .base import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = ["*"]  # TODO: 추후 도메인 설정 후 변경

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]  # TODO: 추후 도메인 설정 후 변경

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]  # TODO: 추후 도메인 설정 후 변경
