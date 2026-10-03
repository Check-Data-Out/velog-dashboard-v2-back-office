from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from ops_tracking.services import find_db_invariant_violations


class Command(BaseCommand):
    help = (
        "운영 DB 불변식(timescaledb 확장·test_* DB 부재) 검사. 위반 시 exit 1."
    )

    def handle(self, *args, **options) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT extname FROM pg_extension")
            extensions = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT datname FROM pg_database")
            databases = [row[0] for row in cursor.fetchall()]

        violations = find_db_invariant_violations(extensions, databases)
        if violations:
            raise CommandError("; ".join(violations))
        self.stdout.write("db invariants ok")
