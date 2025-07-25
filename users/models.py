from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
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
    username = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="velog 에서 사용자가 지정한 이름입니다.",
        verbose_name="사용자 이름",
    )
    thumbnail = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="velog 에서 사용자가 지정한 thumbnail url 값입니다.",
        verbose_name="사용자 썸네일",
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


def default_expires_at() -> timezone.datetime:
    return now() + timezone.timedelta(minutes=5)


class QRLoginToken(models.Model):  # type: ignore
    token = models.CharField(
        max_length=10, unique=True, verbose_name="로그인용 QR 토큰"
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="qr_login_tokens",
        verbose_name="로그인 요청한 사용자",
        null=False,
    )
    created_at = models.DateTimeField(
        default=now,
        help_text="QR Code 생성 일시",
    )
    expires_at = models.DateTimeField(
        default=default_expires_at,
        help_text="QR Code 유효 기간을 의미합니다. 기본값으로  5분 후 시간으로 자동 설정 됩니다.",
        verbose_name="QR Code 유효 기간",
    )
    is_used = models.BooleanField(default=False, verbose_name="사용 여부")
    ip_address = models.CharField(
        max_length=45, null=True, blank=True, verbose_name="요청한 IP 주소"
    )
    user_agent = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="요청한 디바이스 정보",
    )

    class Meta:
        verbose_name = "QR 로그인 토큰"
        verbose_name_plural = "QR 로그인 토큰 목록"
        indexes = [
            models.Index(fields=["token"]),
        ]

    def __str__(self) -> str:
        return f"QR 로그인 토큰({self.token}) - {self.user.email if self.user else 'Anonymous'}"

    def is_valid(self) -> bool:
        """QR 코드가 유효한지 확인"""
        return not self.is_used and self.expires_at > now()
