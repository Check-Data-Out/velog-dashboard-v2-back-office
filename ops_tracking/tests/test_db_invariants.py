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
            constraints=["posts_pds_post_date_uniq"],
        )
        == []
    )


def test_timescaledb_extension_and_test_database_are_both_reported():
    violations = find_db_invariant_violations(
        extensions=["plpgsql", "timescaledb"],
        databases=["postgres", "test_postgres"],
        constraints=["posts_pds_post_date_uniq"],
    )

    assert len(violations) == 2
    assert any("timescaledb" in v for v in violations)
    assert any("test_postgres" in v for v in violations)


def test_missing_daily_stats_unique_constraint_is_reported():
    """일별 통계 유니크 제약이 없으면 이름을 담아 알리는지.

    마이그레이션 미적용, 인덱스 생성 실패 후 방치, 수동 삭제 모두 같은 신호다.
    """
    violations = find_db_invariant_violations(
        extensions=["plpgsql"], databases=["postgres"], constraints=[]
    )

    assert len(violations) == 1
    assert "posts_pds_post_date_uniq" in violations[0]


@pytest.mark.django_db
def test_command_fails_on_pytest_test_database():
    """pytest 가 만든 test_* DB 자체가 위반이므로 실제 쿼리 경로로 실패를 확인한다.

    테스트 DB 는 마이그레이션으로 만들어지므로 0008 이 만든 유니크 제약은 위반에
    나오지 않아야 한다(제약 이름·종류까지 실제 카탈로그로 확인).
    """
    with pytest.raises(CommandError, match="test_") as exc_info:
        call_command("check_db_invariants")

    assert "posts_pds_post_date_uniq" not in str(exc_info.value)
