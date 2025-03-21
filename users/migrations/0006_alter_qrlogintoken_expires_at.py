# Generated by Django 5.1.6 on 2025-03-20 00:23

from django.db import migrations, models

import users.models


class Migration(migrations.Migration):
    dependencies = [
        (
            "users",
            "0005_remove_user_qr_login_token_qrlogintoken_user_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="qrlogintoken",
            name="expires_at",
            field=models.DateTimeField(
                default=users.models.default_expires_at,
                help_text="QR Code 유효 기간(기본값 5분 후)",
            ),
        ),
    ]
