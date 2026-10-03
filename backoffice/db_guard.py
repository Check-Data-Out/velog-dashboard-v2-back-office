"""pytest 가 운영 DB 에 테스트 DB 를 만들지 못하게 막는 가드.

2025-09 운영 접속정보로 pytest 가 실행돼 운영 Supabase 에 `test_postgres` 가
생성·잔존했다. 테스트 DB 는 로컬(또는 CI 서비스 컨테이너)에서만 만든다.
"""

SAFE_TEST_DB_HOSTS = frozenset({"", "localhost", "127.0.0.1", "db"})


def is_safe_test_db_host(host: str) -> bool:
    return host in SAFE_TEST_DB_HOSTS


def resolve_test_db_host(settings_host: str, environ: dict[str, str]) -> str:
    """libpq 가 실제로 접속할 HOST.

    PGHOSTADDR 는 host 보다 우선한다. PGSERVICE 는 서비스 파일이 host/hostaddr 를
    바꿀 수 있어 판정할 수 없으므로 로컬이 아닌 값으로 돌려줘 거부되게 한다.
    설정 HOST 가 비면 libpq 가 PGHOST 로 접속한다.
    """
    if environ.get("PGHOSTADDR"):
        return environ["PGHOSTADDR"]
    if environ.get("PGSERVICE"):
        return f"service={environ['PGSERVICE']}"
    return settings_host or environ.get("PGHOST", "")
