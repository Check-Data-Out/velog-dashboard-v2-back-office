# Generated by Django 5.1.4 on 2024-12-22 10:26

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("posts", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="PostStatistics",
        ),
    ]
