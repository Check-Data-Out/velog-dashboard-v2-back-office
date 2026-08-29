from django.db import migrations

INDEX_NAME = "posts_pds_date_post_idx"

# date 를 선행 컬럼으로 갖는 인덱스가 없어 date 단독 조건 조회가 전부 전체 스캔이 된다.
# 기존 posts_pds_post_date_idx 는 (post_id, date DESC) 라 date 조건에는 쓸 수 없다.
CREATE_INDEX_SQL = (
    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
    "ON posts_postdailystatistics (date, post_id);"
)
DROP_INDEX_SQL = f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};"


def create_index(apps, schema_editor):
    # CONCURRENTLY 는 PostgreSQL 전용 구문이라 sqlite 등 다른 백엔드에서는 건너뛴다.
    # (settings 기본 엔진이 sqlite3 라 가드가 없으면 로컬 migrate 가 깨진다)
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_INDEX_SQL)


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_INDEX_SQL)


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
