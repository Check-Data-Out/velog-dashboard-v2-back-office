from django.core.exceptions import ValidationError
from django.db import models

from common.models import TimeStampedModel
from utils.utils import generate_random_group_id


class User(TimeStampedModel):
    """
    대시보드 사용자 모델
    """

    velog_uuid = models.UUIDField(
        blank=False, null=False, unique=True, verbose_name="사용자 UUID"
    )
    access_token = models.TextField(
        blank=False, null=False, verbose_name="Access Token"
    )
    refresh_token = models.TextField(
        blank=False, null=False, verbose_name="Refresh Token"
    )
    group_id = models.IntegerField(
        blank=True,
        null=False,
        default=generate_random_group_id,
        verbose_name="그룹 ID",
    )
    email = models.EmailField(
        blank=True, null=True, unique=False, verbose_name="이메일"
    )
    is_active = models.BooleanField(
        default=True, null=False, verbose_name="활성 여부"
    )

    def __str__(self) -> str:
        return f"{self.velog_uuid}"

    def clean(self) -> None:
        if (
            self.email
            and self.email != ""
            and User.objects.exclude(pk=self.pk)
            .filter(email=self.email)
            .exists()
        ):
            raise ValidationError({"email": "이미 존재하는 이메일입니다."})

    class Meta:
        verbose_name = "사용자"
        verbose_name_plural = "사용자 목록"
