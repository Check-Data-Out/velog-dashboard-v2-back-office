from django.contrib.auth import get_user_model
from django.db import models

from users.models import User;
from common.models import TimeStampedModel


class QRLoginToken(TimeStampedModel):
    token = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="로그인용 QR 토큰"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        verbose_name="로그인 요청한 사용자"
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
        return f"QR 로그인 토큰({self.token}) - {self.user.username if self.user else 'Anonymous'}"

    def is_valid(self):
        """QR 코드가 유효한지 확인"""
        from django.utils.timezone import now
        return not self.is_used and self.expires_at > now()
