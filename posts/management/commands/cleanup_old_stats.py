"""PostDailyStatistics 의 6개월 이전 데이터를 drop_chunks 로 정리하는 배치."""

import logging
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from modules.noti.slack_client import notify_ops
from modules.redis.client import get_redis_client
from posts.models import PostDailyStatistics

logger = logging.getLogger(__name__)

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
            raise CommandError(
                f"--retention-months must be positive (got {months})"
            )
        if chunk <= 0:
            raise CommandError(f"--chunk must be positive (got {chunk})")

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

        started_at = time.monotonic()
        redis_client = self._safe_redis_client()
        try:
            dropped_chunks, cutoff_ts = self._drop_chunks_and_get_cutoff(
                months
            )
            orm_deleted = self._orm_fallback(cutoff_ts, chunk)
        except Exception as e:
            logger.exception("cleanup_old_stats failed")
            notify_ops(
                text=f"[velog-dashboard-v2] PostDailyStatistics 정리 실패: {e}",
                cooldown_key=COOLDOWN_KEY,
                redis_client=redis_client,
            )
            raise CommandError(str(e)) from e
        elapsed = time.monotonic() - started_at
        logger.info(
            "cleanup_old_stats: cutoff=%s dropped_chunks=%d orm_deleted=%d elapsed=%.2fs",
            cutoff_ts.isoformat(),
            dropped_chunks,
            orm_deleted,
            elapsed,
        )
        notify_ops(
            text=(
                f"[velog-dashboard-v2] PostDailyStatistics 정리 완료\n"
                f"- cutoff: {cutoff_ts.isoformat()}\n"
                f"- dropped_chunks: {dropped_chunks}\n"
                f"- orm_deleted: {orm_deleted}\n"
                f"- elapsed: {elapsed:.2f}s"
            ),
            cooldown_key=COOLDOWN_KEY,
            redis_client=redis_client,
        )
        self.stdout.write(
            f"dropped {dropped_chunks} chunks, {orm_deleted} orm rows"
        )

    @staticmethod
    def _safe_redis_client():
        """Redis 미가용 시 워닝만 남기고 None 반환 (배치는 계속)."""
        try:
            return get_redis_client()
        except Exception as e:
            logger.warning("redis unavailable: %s", e)
            return None

    def _drop_chunks_and_get_cutoff(self, months: int) -> tuple[int, datetime]:
        """drop_chunks 호출 + cutoff_ts 산출.

        Django 기본 autocommit 환경에서 `SET LOCAL` 이 효과를 가지려면
        명시적 트랜잭션이 필요하므로 transaction.atomic() 으로 감싼다.
        """
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = 0")
            cursor.execute(
                "SELECT drop_chunks(%s, older_than => NOW() - make_interval(months => %s))",
                [HYPERTABLE_NAME, months],
            )
            dropped_rows = cursor.fetchall()
            cursor.execute(
                "SELECT NOW() - make_interval(months => %s)", [months]
            )
            cutoff_ts = cursor.fetchone()[0]
        return len(dropped_rows), cutoff_ts

    def _orm_fallback(self, cutoff_ts: datetime, chunk: int) -> int:
        """drop_chunks 후 chunk 경계 안쪽 잔여 행을 ORM 으로 정리."""
        remaining = PostDailyStatistics.objects.filter(
            date__lt=cutoff_ts
        ).count()
        if remaining == 0:
            return 0
        max_iterations = math.ceil(remaining / chunk) + 10
        orm_deleted = 0
        for _ in range(max_iterations):
            ids = list(
                PostDailyStatistics.objects.filter(
                    date__lt=cutoff_ts
                ).values_list("pk", flat=True)[:chunk]
            )
            if not ids:
                break
            deleted, _ = PostDailyStatistics.objects.filter(
                pk__in=ids
            ).delete()
            if deleted == 0:
                logger.warning("orm fallback: delete returned 0 — abort")
                break
            orm_deleted += deleted
        else:
            logger.warning(
                "orm fallback: max_iterations=%d reached without drain",
                max_iterations,
            )
        return orm_deleted
