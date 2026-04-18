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
