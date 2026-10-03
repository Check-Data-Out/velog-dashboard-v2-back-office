import pytest

from backoffice.db_guard import is_safe_test_db_host


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
