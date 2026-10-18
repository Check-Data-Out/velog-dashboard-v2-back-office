from django.core.management.base import BaseCommand, CommandError
from django.db import connection

DAILY_STATS_UNIQUE_CONSTRAINT = "posts_pds_post_date_uniq"


def find_db_invariant_violations(
    extensions: list[str], databases: list[str], constraints: list[str]
) -> list[str]:
    """운영 DB 가 지켜야 할 불변식 위반 목록을 반환한다.

    - timescaledb 확장: Apache 빌드의 job 3 이 실패 로그를 무한히 쌓는다.
    - test_* DB: pytest 가 운영 DB 에 남긴 테스트 DB.
    - 일별 통계 (post_id, date) 유니크 제약: 없으면 같은 날 행이 중복될 수 있고,
      중복된 게시글은 그날 통계 갱신이 계속 실패한다.
    """
    violations = []
    if "timescaledb" in extensions:
        violations.append("timescaledb 확장이 존재합니다")
    violations += [
        f"테스트 DB 가 존재합니다: {name}"
        for name in databases
        if name.startswith("test_")
    ]
    if DAILY_STATS_UNIQUE_CONSTRAINT not in constraints:
        violations.append(
            f"일별 통계 유니크 제약이 없습니다: {DAILY_STATS_UNIQUE_CONSTRAINT}"
        )
    return violations


class Command(BaseCommand):
    help = (
        "운영 DB 불변식(timescaledb 확장·test_* DB 부재, 일별 통계 유니크 제약 "
        "존재) 검사. 위반 시 exit 1."
    )

    def handle(self, *args, **options) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT extname FROM pg_extension")
            extensions = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT datname FROM pg_database")
            databases = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT conname FROM pg_constraint"
                " WHERE conrelid = 'posts_postdailystatistics'::regclass"
                " AND conname = %s AND contype = 'u'",
                [DAILY_STATS_UNIQUE_CONSTRAINT],
            )
            constraints = [row[0] for row in cursor.fetchall()]

        violations = find_db_invariant_violations(
            extensions, databases, constraints
        )
        if violations:
            raise CommandError("; ".join(violations))
        self.stdout.write("db invariants ok")
