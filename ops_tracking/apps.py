from django.apps import AppConfig


class OpsTrackingConfig(AppConfig):
    """운영(stats refresh) 요청 추적 모델/서비스를 담는 앱."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "ops_tracking"
    verbose_name = "운영 추적"
