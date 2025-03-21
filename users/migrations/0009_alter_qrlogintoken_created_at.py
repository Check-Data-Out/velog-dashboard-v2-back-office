# Generated by Django 5.1.6 on 2025-03-21 00:15

import datetime

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0008_qrlogintoken_created_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="qrlogintoken",
            name="created_at",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2025,
                    3,
                    21,
                    0,
                    15,
                    27,
                    506659,
                    tzinfo=datetime.timezone.utc,
                ),
                help_text="QR Code 생성 일시",
            ),
        ),
    ]
