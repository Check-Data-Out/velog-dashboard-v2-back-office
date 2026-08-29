from django.db import migrations


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY 는 트랜잭션 블록 안에서 실행할 수 없다.
    # posts_postdailystatistics 는 약 7.2M 행이고 집계 배치가 50분 주기로 상시 쓰기를 하므로,
    # 일반 CREATE INDEX 의 쓰기 락(ACCESS EXCLUSIVE)을 피하려면 CONCURRENTLY 가 필요하다.
    atomic = False

    dependencies = [
        ("posts", "0006_postdailystatistics_post_date_idx"),
    ]

    operations = [
        # date 를 선행 컬럼으로 갖는 인덱스가 없어 date 단독 조건 조회가 전부 전체 스캔이 된다.
        # 기존 posts_pds_post_date_idx 는 (post_id, date DESC) 라 date 조건에는 쓸 수 없다.
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "posts_pds_date_post_idx "
                "ON posts_postdailystatistics (date, post_id);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS posts_pds_date_post_idx;"
            ),
        ),
    ]
