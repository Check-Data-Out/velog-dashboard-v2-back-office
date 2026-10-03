from django.db import migrations

TABLE_NAME = "posts_postdailystatistics"
INDEX_NAME = "posts_pds_date_post_idx"

# date 를 선행 컬럼으로 갖는 인덱스가 없어 date 단독 조건 조회가 전부 전체 스캔이 된다.
# 기존 posts_pds_post_date_idx 는 (post_id, date DESC) 라 date 조건에는 쓸 수 없다.
INDEX_COLUMNS = "(date, post_id)"

IS_HYPERTABLE_SQL = (
    "SELECT EXISTS ("
    "  SELECT 1 FROM timescaledb_information.hypertables"
    "  WHERE hypertable_name = %s"
    ");"
)


def _is_hypertable(schema_editor) -> bool:
    """timescaledb 확장이 없거나 hypertables 뷰 조회가 실패하면 일반 테이블로 간주한다."""
    try:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(IS_HYPERTABLE_SQL, [TABLE_NAME])
            row = cursor.fetchone()
            return bool(row and row[0])
    except Exception:
        return False


def create_index(apps, schema_editor):
    # CONCURRENTLY 는 PostgreSQL 전용 구문이라 sqlite 등 다른 백엔드에서는 건너뛴다.
    # (settings 기본 엔진이 sqlite3 라 가드가 없으면 로컬 migrate 가 깨진다)
    if schema_editor.connection.vendor != "postgresql":
        return

    # 운영 DB·CI 의 이 테이블은 일반 테이블이라 CONCURRENTLY 로 쓰기 락을 피한다.
    # 단 timescale 백엔드로 만든 기존 DB 에서는 하이퍼테이블이고, 하이퍼테이블은
    # CONCURRENTLY 를 거부하므로 런타임에 판정한다.
    concurrently = "" if _is_hypertable(schema_editor) else "CONCURRENTLY "
    schema_editor.execute(
        f"CREATE INDEX {concurrently}IF NOT EXISTS {INDEX_NAME} "
        f"ON {TABLE_NAME} {INDEX_COLUMNS};"
    )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    concurrently = "" if _is_hypertable(schema_editor) else "CONCURRENTLY "
    schema_editor.execute(f"DROP INDEX {concurrently}IF EXISTS {INDEX_NAME};")


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY 는 트랜잭션 블록 안에서 실행할 수 없다.
    # posts_postdailystatistics 는 약 7.2M 행이고 집계 배치가 50분 주기로 상시 쓰기를 하므로,
    # 일반 CREATE INDEX 의 쓰기 락(ACCESS EXCLUSIVE)을 피하려면 CONCURRENTLY 가 필요하다.
    atomic = False

    dependencies = [
        ("posts", "0006_postdailystatistics_post_date_idx"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
