from .local import *  # noqa: F401, F403

# test-ci 에서 test dbms 로 timesacleDB 를 사용하지 못함
# 이를 위해 test 환경은 부득이한 local-dbms 를 사용하게 해야 함
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}
