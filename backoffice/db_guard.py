"""pytest 가 운영 DB 에 테스트 DB 를 만들지 못하게 막는 가드.

2025-09 운영 접속정보로 pytest 가 실행돼 운영 Supabase 에 `test_postgres` 가
생성·잔존했다. 테스트 DB 는 로컬(또는 CI 서비스 컨테이너)에서만 만든다.
"""

SAFE_TEST_DB_HOSTS = frozenset({"", "localhost", "127.0.0.1", "db"})


def is_safe_test_db_host(host: str) -> bool:
    return host in SAFE_TEST_DB_HOSTS
