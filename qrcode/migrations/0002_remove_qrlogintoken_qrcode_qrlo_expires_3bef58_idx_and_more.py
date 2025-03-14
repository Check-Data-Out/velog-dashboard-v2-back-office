# Generated by Django 5.1.6 on 2025-03-14 23:15

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qrcode', '0001_initial'),
        ('users', '0002_alter_user_email'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='qrlogintoken',
            name='qrcode_qrlo_expires_3bef58_idx',
        ),
        migrations.AlterField(
            model_name='qrlogintoken',
            name='expires_at',
            field=models.DateTimeField(help_text='QR Code 유효 기간(기본값 5분 후)'),
        ),
        migrations.AlterField(
            model_name='qrlogintoken',
            name='user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='users.user', verbose_name='로그인 요청한 사용자'),
        ),
    ]
