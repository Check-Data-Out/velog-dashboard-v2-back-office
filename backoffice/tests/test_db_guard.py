import pytest

from backoffice.db_guard import is_safe_test_db_host, resolve_test_db_host


@pytest.mark.parametrize("host", ["", "localhost", "127.0.0.1", "db"])
def test_local_hosts_are_safe_for_test_db(host):
    assert is_safe_test_db_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "aws-0-ap-northeast-2.pooler.supabase.com",
        "db.abcdefghijkl.supabase.co",
        "10.0.0.5",
    ],
)
def test_remote_hosts_are_rejected_for_test_db(host):
    assert not is_safe_test_db_host(host)


def test_empty_host_resolves_to_pghost():
    """HOST 가 비면 libpq 가 PGHOST 로 접속하므로 그 값으로 판정해야 한다."""
    assert (
        resolve_test_db_host("", {"PGHOST": "db.abcdefghijkl.supabase.co"})
        == "db.abcdefghijkl.supabase.co"
    )


def test_settings_host_wins_over_pghost():
    assert (
        resolve_test_db_host("localhost", {"PGHOST": "remote"}) == "localhost"
    )


def test_pghostaddr_wins_over_settings_host():
    """libpq 는 hostaddr 가 있으면 host 대신 그 주소로 접속한다."""
    assert (
        resolve_test_db_host("localhost", {"PGHOSTADDR": "10.0.0.5"})
        == "10.0.0.5"
    )


def test_pgservice_is_rejected():
    """서비스 파일이 host/hostaddr 를 바꿀 수 있어 접속 대상을 판정할 수 없다."""
    host = resolve_test_db_host("localhost", {"PGSERVICE": "prod"})
    assert not is_safe_test_db_host(host)
