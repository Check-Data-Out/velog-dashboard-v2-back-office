from django.contrib.auth import get_user_model
from django.db import models

from common.models import TimeStampedModel

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
