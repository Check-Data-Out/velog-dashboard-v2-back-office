import os
from pathlib import Path

import environ

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_env_path = os.path.join(_BASE_DIR, ".env")
if not os.path.exists(_env_path):
    raise EnvironmentError(
        f".env file not found at {_env_path}. Copy from .env.sample."
    )
environ.Env.read_env(_env_path)

from .base import *  # noqa: E402, F401, F403

DEBUG = True

INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]

CORS_ALLOW_ALL_ORIGINS = True

# DATABASES["prod"] = env.db()  # noqa: F405
