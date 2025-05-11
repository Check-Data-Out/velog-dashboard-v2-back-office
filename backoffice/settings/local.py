from .base import *  # noqa: F401, F403

DEBUG = True

INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]

CORS_ALLOW_ALL_ORIGINS = True

DATABASES["prod"] = env.db()  # noqa: F405
