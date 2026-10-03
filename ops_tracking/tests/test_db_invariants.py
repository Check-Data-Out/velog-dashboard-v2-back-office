import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from ops_tracking.management.commands.check_db_invariants import (
    find_db_invariant_violations,
)


def test_no_violation_without_timescaledb_and_test_databases():
    assert (
        find_db_invariant_violations(
            extensions=["plpgsql", "pg_stat_statements"],
            databases=["postgres", "template1"],
        )
        == []
    )


def test_timescaledb_extension_and_test_database_are_violations():
    violations = find_db_invariant_violations(
        extensions=["plpgsql", "timescaledb"],
        databases=["postgres", "test_postgres"],
    )

    assert len(violations) == 2
    assert "timescaledb" in violations[0]
    assert "test_postgres" in violations[1]


@pytest.mark.django_db
def test_command_fails_on_pytest_test_database():
    """pytest 가 만든 test_* DB 자체가 위반이므로 실제 쿼리 경로로 실패를 확인한다."""
    with pytest.raises(CommandError, match="test_"):
        call_command("check_db_invariants")
