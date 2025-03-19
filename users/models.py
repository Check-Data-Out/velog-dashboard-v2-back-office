from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import now

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
    qr_login_token = models.OneToOneField(
        "users.QRLoginToken",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_qr_token",
        verbose_name="QR 로그인 토큰"
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



class QRLoginToken(models.Model):
    token = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="로그인용 QR 토큰"
    )
    expires_at = models.DateTimeField(
        help_text="QR Code 유효 기간(기본값 5분 후)"
    )
    is_used = models.BooleanField(
        default=False,
        verbose_name="사용 여부"
    )
    ip_address = models.CharField(
        max_length=45,
        null=True,
        blank=True,
        verbose_name="요청한 IP 주소"
    )
    user_agent = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="요청한 디바이스 정보"
    )

    class Meta:
        verbose_name = "QR 로그인 토큰"
        verbose_name_plural = "QR 로그인 토큰 목록"
        indexes = [
            models.Index(fields=["token"]),
        ]
    
    def __str__(self):
        return f"QR 로그인 토큰({self.token}) - {self.user.email if self.user else 'Anonymous'}"

    def is_valid(self):
        """QR 코드가 유효한지 확인"""
        return not self.is_used and self.expires_at > now()