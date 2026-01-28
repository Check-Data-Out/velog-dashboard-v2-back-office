import os
from pathlib import Path

import environ

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_env_path = os.path.join(_BASE_DIR, ".env.prod")
if not os.path.exists(_env_path):
    raise EnvironmentError(f".env.prod file not found at {_env_path}.")
environ.Env.read_env(_env_path)

from .base import *  # noqa: E402, F401, F403

ALLOWED_HOSTS = [
    "admin-vd2.kro.kr",
    "134.185.98.129",  # 서버쪽 IP
]

DEBUG = False

INTERNAL_IPS = []  # 프로덕션 환경에서는 빈 리스트로 설정

CSRF_TRUSTED_ORIGINS = ["https://admin-vd2.kro.kr"]

CORS_ALLOWED_ORIGINS = ["https://admin-vd2.kro.kr"]
