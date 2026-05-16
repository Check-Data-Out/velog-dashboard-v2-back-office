"""PostDailyStatistics 의 6개월 이전 데이터를 drop_chunks 로 정리하는 배치."""

from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from posts.models import PostDailyStatistics

RETENTION_MONTHS_DEFAULT = 6
ORM_CHUNK_DEFAULT = 5000
COOLDOWN_KEY = "cleanup-old-stats"
KST = ZoneInfo("Asia/Seoul")
HYPERTABLE_NAME = "posts_postdailystatistics"


class Command(BaseCommand):
    help = "PostDailyStatistics 의 6개월 이전 데이터를 drop_chunks 로 정리."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--retention-months",
            type=int,
            default=RETENTION_MONTHS_DEFAULT,
            help="보존 개월 수 (기본 6)",
        )
        parser.add_argument(
            "--chunk",
            type=int,
            default=ORM_CHUNK_DEFAULT,
            help="ORM 폴백 시 1회 DELETE chunk 크기",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="삭제 없이 대상만 출력",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="KST 1~2일 day-guard 우회 (수동 실행 전용)",
        )

    def handle(self, *args, **options) -> None:
        months = options["retention_months"]
        chunk = options["chunk"]
        if months <= 0:
            raise SystemExit(
                f"--retention-months must be positive (got {months})"
            )
        if chunk <= 0:
            raise SystemExit(f"--chunk must be positive (got {chunk})")

        if not options["force"] and timezone.now().astimezone(KST).day not in (
            1,
            2,
        ):
            self.stdout.write("not the 1st/2nd of month KST, skipping")
            return

        if options["dry_run"]:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT NOW() - make_interval(months => %s)", [months]
                )
                cutoff_ts = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT count(*) FROM show_chunks(%s, older_than => %s)",
                    [HYPERTABLE_NAME, cutoff_ts],
                )
                chunk_count = cursor.fetchone()[0]
            row_count = PostDailyStatistics.objects.filter(
                date__lt=cutoff_ts
            ).count()
            self.stdout.write(
                f"dry-run cutoff={cutoff_ts.isoformat()} "
                f"chunks={chunk_count} rows~={row_count}"
            )
            return

        self.stdout.write("would proceed (drop_chunks impl in next phase)")
