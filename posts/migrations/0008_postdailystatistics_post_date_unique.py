from django.db import migrations, models

TABLE_NAME = "posts_postdailystatistics"
CONSTRAINT_NAME = "posts_pds_post_date_uniq"
COLUMNS = "(post_id, date)"

CONSTRAINT_EXISTS_SQL = (
    "SELECT EXISTS ("
    "  SELECT 1 FROM pg_constraint"
    f"  WHERE conrelid = '{TABLE_NAME}'::regclass"
    "    AND conname = %s AND contype = 'u'"
    ");"
)
DUPLICATE_GROUPS_SQL = (
    "SELECT count(*) FROM ("
    f"  SELECT 1 FROM {TABLE_NAME} GROUP BY post_id, date HAVING count(*) > 1"
    ") AS duplicated;"
)
# 이 테이블의 인덱스만 본다. 다른 테이블에 같은 이름 인덱스가 있으면 건드리지 않는다
# (적용 때는 뒤의 CREATE INDEX 가 이름 충돌로 멈춘다).
INDEX_VALID_SQL = (
    "SELECT indisvalid FROM pg_index"
    " WHERE indexrelid = to_regclass(%s)"
    f"  AND indrelid = '{TABLE_NAME}'::regclass;"
)
# 그룹마다 min(id) 한 행만 남긴다(같은 그룹의 행은 값이 같아 정보 손실이 없다).
DEDUPE_SQL = (
    f"DELETE FROM {TABLE_NAME} s USING ("
    f"SELECT post_id, date, min(id) AS keep_id FROM {TABLE_NAME} "
    "GROUP BY post_id, date HAVING count(*) > 1) d "
    "WHERE s.post_id = d.post_id AND s.date = d.date AND s.id <> d.keep_id;"
)


def _fetch_one(schema_editor, sql, params=None):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def _session_timeouts(schema_editor) -> list[str]:
    """인덱스 작업 동안 0 으로 둘 세션 타임아웃.

    CREATE/DROP INDEX CONCURRENTLY 는 이 테이블을 쓰는 트랜잭션과 오래된 스냅샷을
    가진 트랜잭션을 기다리고, 내부에서 트랜잭션을 여러 번 연다. 이 대기와 트랜잭션도
    각 타임아웃 대상이라 0 이 아니면 중간에 끊겨 INVALID 인덱스가 남는다. 운영 역할의
    기본값에 기대지 않는다. transaction_timeout 은 PostgreSQL 17 부터 있다.
    """
    names = ["statement_timeout", "lock_timeout"]
    if schema_editor.connection.pg_version >= 170000:
        names.append("transaction_timeout")
    return names


def create_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        # sqlite 등 로컬 백엔드는 같은 이름의 유니크 인덱스로 대신한다.
        schema_editor.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {CONSTRAINT_NAME} "
            f"ON {TABLE_NAME} {COLUMNS};"
        )
        return

    # 승격까지 끝난 상태면 할 일이 없다(--fake 로 기록만 되돌린 경우 등).
    if _fetch_one(schema_editor, CONSTRAINT_EXISTS_SQL, [CONSTRAINT_NAME])[0]:
        return

    timeouts = _session_timeouts(schema_editor)
    try:
        for name in timeouts:
            schema_editor.execute(f"SET {name} = 0;")

        duplicated = _fetch_one(schema_editor, DUPLICATE_GROUPS_SQL)[0]
        if duplicated:
            raise RuntimeError(
                f"{TABLE_NAME} 에 같은 (post_id, date) 행이 있는 그룹이 "
                f"{duplicated}개 있어 유니크 제약을 만들 수 없습니다. "
                "README 의 '일별 통계 (post_id, date) 중복 정리' 절을 따라 정리한 "
                "뒤 다시 migrate 하세요. 그룹마다 min(id) 만 남기는 SQL: "
                f"{DEDUPE_SQL} --fake 로 건너뛰면 제약 없이 적용 기록만 남으니 "
                "쓰지 마세요."
            )

        # 직전 실행이 끊겨 남은 인덱스: INVALID 면 지우고 다시 만들고, VALID 면
        # 승격만 한다. CREATE … IF NOT EXISTS 는 INVALID 를 그대로 두고 통과한다.
        row = _fetch_one(schema_editor, INDEX_VALID_SQL, [CONSTRAINT_NAME])
        if row is not None and not row[0]:
            schema_editor.execute(
                f"DROP INDEX CONCURRENTLY {CONSTRAINT_NAME};"
            )
            row = None
        if row is None:
            schema_editor.execute(
                f"CREATE UNIQUE INDEX CONCURRENTLY {CONSTRAINT_NAME} "
                f"ON {TABLE_NAME} {COLUMNS};"
            )

        # 승격은 카탈로그만 바꿔 즉시 끝나지만 ACCESS EXCLUSIVE 를 기다리는 동안
        # 이 테이블의 뒤이은 읽기·쓰기가 줄을 선다. 그래서 대기를 3초로 묶는다.
        # 실패해도 VALID 인덱스가 남아 다시 migrate 하면 승격만 한다.
        schema_editor.execute("SET lock_timeout = '3s';")
        schema_editor.execute(
            f"ALTER TABLE {TABLE_NAME} ADD CONSTRAINT {CONSTRAINT_NAME} "
            f"UNIQUE USING INDEX {CONSTRAINT_NAME};"
        )
    finally:
        for name in timeouts:
            schema_editor.execute(f"RESET {name};")


def drop_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        schema_editor.execute(f"DROP INDEX IF EXISTS {CONSTRAINT_NAME};")
        return

    timeouts = _session_timeouts(schema_editor)
    try:
        for name in timeouts:
            schema_editor.execute(f"SET {name} = 0;")
        # 제약이 인덱스를 소유하므로 인덱스도 함께 지워진다.
        schema_editor.execute("SET lock_timeout = '3s';")
        schema_editor.execute(
            f"ALTER TABLE {TABLE_NAME} DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME};"
        )
        # 승격 전에 끊겨 이 테이블에 인덱스만 남은 상태를 정리한다.
        if _fetch_one(schema_editor, INDEX_VALID_SQL, [CONSTRAINT_NAME]):
            schema_editor.execute("SET lock_timeout = 0;")
            schema_editor.execute(
                f"DROP INDEX CONCURRENTLY IF EXISTS {CONSTRAINT_NAME};"
            )
    finally:
        for name in timeouts:
            schema_editor.execute(f"RESET {name};")


class Migration(migrations.Migration):
    # CREATE/DROP INDEX CONCURRENTLY 는 트랜잭션 블록 안에서 실행할 수 없다.
    # Django 에는 유니크 제약을 무중단으로 만드는 연산이 없어(AddConstraint 는
    # 인덱스를 만드는 동안 읽기·쓰기를 모두 막는다) 상태와 DB 작업을 나눈다.
    atomic = False

    dependencies = [
        ("posts", "0007_postdailystatistics_date_post_idx"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(create_constraint, drop_constraint),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="postdailystatistics",
                    constraint=models.UniqueConstraint(
                        fields=["post", "date"], name=CONSTRAINT_NAME
                    ),
                ),
            ],
        ),
    ]
