from django.apps import AppConfig


class QueueMonitorConfig(AppConfig):
    """Redis 기반 stats-refresh 큐 운영(대시보드/DLQ) 앱."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "queue_monitor"
    verbose_name = "큐 모니터"
