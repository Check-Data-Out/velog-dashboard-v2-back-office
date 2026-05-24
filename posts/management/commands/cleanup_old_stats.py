import logging
import math
import os
import time
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.utils import DatabaseError

from modules.noti.slack_client import notify_ops
from modules.redis.client import get_redis_client
from posts.models import PostDailyStatistics

logger = logging.getLogger(__name__)

RETENTION_MONTHS_DEFAULT = 6
ORM_CHUNK_DEFAULT = 5000
COOLDOWN_KEY = "cleanup-old-stats"
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

    def handle(self, *args, **options) -> None:
        months = options["retention_months"]
        chunk = options["chunk"]
        if months <= 0:
            raise CommandError(
                f"--retention-months must be positive (got {months})"
            )
        if chunk <= 0:
            raise CommandError(f"--chunk must be positive (got {chunk})")

        if options["dry_run"]:
            cutoff_ts = self._get_cutoff(months)
            chunk_count = self._count_chunks_safely(cutoff_ts)
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
            self._notify_ops_safely(
                text=f"[velog-dashboard-v2] PostDailyStatistics 정리 실패: {e}",
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
        self._notify_ops_safely(
            text=(
                f"[velog-dashboard-v2] PostDailyStatistics 정리 완료\n"
                f"- cutoff: {cutoff_ts.isoformat()}\n"
                f"- dropped_chunks: {dropped_chunks}\n"
                f"- orm_deleted: {orm_deleted}\n"
                f"- elapsed: {elapsed:.2f}s"
            ),
            redis_client=redis_client,
        )
        self.stdout.write(
            f"dropped {dropped_chunks} chunks, {orm_deleted} orm rows"
        )

    @staticmethod
    def _notify_ops_safely(text: str, redis_client) -> None:
        """notify_ops 가 raise 해도 배치 결과가 오염되지 않도록 best-effort 래핑."""
        try:
            notify_ops(
                text=text,
                cooldown_key=COOLDOWN_KEY,
                redis_client=redis_client,
            )
        except Exception:
            logger.warning("notify_ops failed", exc_info=True)

    @staticmethod
    def _safe_redis_client():
        """Slack cooldown 용 Redis 가 명시 설정된 경우에만 연결한다."""
        if not os.environ.get("SLACK_OPS_WEBHOOK", "").strip():
            logger.info("SLACK_OPS_WEBHOOK not set; skipping Redis cooldown")
            return None
        redis_host = os.environ.get("REDIS_HOST")
        if redis_host is not None and not redis_host.strip():
            logger.info("REDIS_HOST not set; skipping Redis cooldown")
            return None
        try:
            return get_redis_client()
        except Exception as e:
            logger.warning("redis unavailable: %s", e)
            return None

    @staticmethod
    def _is_optional_timescale_error(error: Exception) -> bool:
        message = str(error).lower()
        return (
            "not a hypertable or a continuous aggregate" in message
            or "function show_chunks" in message
            or "function drop_chunks" in message
        )

    @staticmethod
    def _get_cutoff(months: int) -> datetime:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT NOW() - make_interval(months => %s)", [months]
            )
            return cursor.fetchone()[0]

    def _count_chunks_safely(self, cutoff_ts: datetime) -> int:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM show_chunks(%s::regclass, older_than => %s)",
                    [HYPERTABLE_NAME, cutoff_ts],
                )
                return cursor.fetchone()[0]
        except DatabaseError as e:
            if not self._is_optional_timescale_error(e):
                raise
            logger.info(
                "show_chunks unavailable for %s; falling back to ORM count: %s",
                HYPERTABLE_NAME,
                e,
            )
            return 0

    def _drop_chunks_and_get_cutoff(self, months: int) -> tuple[int, datetime]:
        """drop_chunks 호출 + cutoff_ts 산출.

        Supabase 운영 DB처럼 일반 테이블이면 TimescaleDB 전용 정리를
        건너뛰고 같은 cutoff 로 ORM fallback 을 계속 실행한다.
        """
        cutoff_ts = self._get_cutoff(months)
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = 0")
                cursor.execute(
                    "SELECT drop_chunks(%s::regclass, older_than => %s)",
                    [HYPERTABLE_NAME, cutoff_ts],
                )
                dropped_rows = cursor.fetchall()
        except DatabaseError as e:
            if not self._is_optional_timescale_error(e):
                raise
            logger.info(
                "drop_chunks unavailable for %s; falling back to ORM delete: %s",
                HYPERTABLE_NAME,
                e,
            )
            return 0, cutoff_ts
        return len(dropped_rows), cutoff_ts

    def _orm_fallback(self, cutoff_ts: datetime, chunk: int) -> int:
        """drop_chunks 후 chunk 경계 안쪽 잔여 행을 ORM 으로 정리."""
        remaining = PostDailyStatistics.objects.filter(
            date__lt=cutoff_ts
        ).count()
        if remaining == 0:
            return 0
        max_iterations = min(math.ceil(remaining / chunk) + 10, 1000)
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
