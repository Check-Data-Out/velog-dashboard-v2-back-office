import uuid

from django.db import models

from users.utils import generate_random_group_id


class User(models.Model):
    velog_uuid = models.UUIDField(
        default=uuid.uuid4, unique=True, verbose_name="사용자 UUID"
    )
    access_token = models.TextField()
    refresh_token = models.TextField()
    group_id = models.IntegerField(
        default=generate_random_group_id, verbose_name="그룹 ID"
    )
    email = models.EmailField(unique=True, verbose_name="이메일")
    is_active = models.BooleanField(default=True, verbose_name="활성 여부")
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="생성 일시"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    def __str__(self):
        return f"{self.velog_uuid}"

    class Meta:
        verbose_name = "사용자"
        verbose_name_plural = "사용자 목록"
