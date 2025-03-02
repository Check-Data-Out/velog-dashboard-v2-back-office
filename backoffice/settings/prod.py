from .base import *  # noqa: F401, F403

ALLOWED_HOSTS = ["admin-vd2.kro.kr"]

DEBUG = False

INTERNAL_IPS = []  # 프로덕션 환경에서는 빈 리스트로 설정

CSRF_TRUSTED_ORIGINS = ["https://admin-vd2.kro.kr"]

CORS_ALLOWED_ORIGINS = ["https://admin-vd2.kro.kr"]
