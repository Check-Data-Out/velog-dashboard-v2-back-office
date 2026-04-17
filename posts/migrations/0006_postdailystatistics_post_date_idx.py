"""Add (post_id, date DESC) composite index to PostDailyStatistics.

Phase 0 Tidy First + Perf: Mixin/Manager 기반 "오늘 통계 누락" 쿼리 (Phase 1)
및 scraping.main 의 get_or_create(post=, date=) 성능 보강.

TimescaleDB hypertable 과의 호환을 위해 IF NOT EXISTS 로 작성.
PostDailyStatistics 가 hypertable 로 선언되어 있더라도
일반 인덱스 생성은 허용됨 (TimescaleDB docs 참조).
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("posts", "0005_post_is_active"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS "
                "posts_pds_post_date_idx "
                "ON posts_postdailystatistics (post_id, date DESC);"
            ),
            reverse_sql=("DROP INDEX IF EXISTS posts_pds_post_date_idx;"),
        ),
    ]
