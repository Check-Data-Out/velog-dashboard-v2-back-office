from django.db import models


class TimeStampedModel(models.Model):
    """
    생성일시, 수정일시 필드 베이스 모델
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성 일시",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정 일시",
    )

    class Meta:
        abstract = True
