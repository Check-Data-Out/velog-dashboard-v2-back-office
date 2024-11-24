from .base import *  # noqa: F401, F403

INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

CORS_ALLOW_ALL_ORIGINS = True
