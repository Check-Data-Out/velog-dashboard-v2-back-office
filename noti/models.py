from django.contrib.auth import get_user_model
from django.db import models

from common.models import TimeStampedModel
from users.models import User as VelogUser

User = get_user_model()


class NotiPost(TimeStampedModel):
    title = models.CharField(
        max_length=255,
        verbose_name="제목",
    )
    content = models.TextField(
        blank=True,
        default="",
        verbose_name="본문",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="체크 해제 시 비공개 상태가 됩니다. (admin에서만 확인 가능)",
        verbose_name="활성 상태",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="작성자",
    )

    def __str__(self):
        return f"[{self.pk}] {self.title}"

    class Meta:
        verbose_name = verbose_name_plural = "공지글"

    def deactivate(self):
        """공지글을 비활성화하는 메서드"""
        self.is_active = False
        self.save()

    def activate(self):
        """공지글을 활성화하는 메서드"""
        self.is_active = True
        self.save()


class NotiMailLog(TimeStampedModel):
    """
    메일 발송 로그
    TODO: [25.05.24] 추후 3개월 이전 로그는 자동으로 삭제되는 로직 추가 필요
    """

    user = models.ForeignKey(
        VelogUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="email_logs",
        verbose_name="수신자",
    )
    subject = models.CharField(max_length=255, verbose_name="메일 제목")
    body = models.TextField(verbose_name="메일 내용")
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name="발송 시간")
    is_success = models.BooleanField(
        default=False, verbose_name="발송 성공 여부"
    )
    error_message = models.TextField(
        blank=True, null=True, verbose_name="오류 메시지"
    )

    class Meta:
        verbose_name = "메일 발송 로그"
        verbose_name_plural = "메일 발송 로그 목록"

    def __str__(self):
        user_email = self.user.email if self.user else "삭제된 사용자"
        return f"{user_email} 메일 발송 ({self.sent_at})"
