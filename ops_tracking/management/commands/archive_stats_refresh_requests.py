"""오래된 StatsRefreshRequest 삭제 (90일 기본)."""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ops_tracking.models import StatsRefreshRequest

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "N 일 이전의 StatsRefreshRequest 행을 배치 삭제."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=90,
            help="보존 일수 (기본 90)",
        )
        parser.add_argument(
            "--chunk", type=int, default=1000, help="1회 DELETE chunk 크기"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="삭제 없이 개수만 출력"
        )

    def handle(self, *args, **options) -> None:
        days = options["older_than_days"]
        chunk = options["chunk"]
        if days <= 0:
            raise SystemExit(
                f"--older-than-days must be a positive integer (got {days})"
            )
        if chunk <= 0:
            raise SystemExit(
                f"--chunk must be a positive integer (got {chunk})"
            )
        cutoff = timezone.now() - timedelta(days=days)
        base_qs = StatsRefreshRequest.objects.filter(created_at__lt=cutoff)
        total = base_qs.count()

        if options["dry_run"]:
            self.stdout.write(
                f"dry-run: would delete {total} rows older than {cutoff.isoformat()}"
            )
            return

        deleted_sum = 0
        while True:
            ids = list(base_qs.values_list("pk", flat=True)[:chunk])
            if not ids:
                break
            deleted, _ = StatsRefreshRequest.objects.filter(
                pk__in=ids
            ).delete()
            deleted_sum += deleted
        self.stdout.write(f"archived {deleted_sum}/{total} rows")
