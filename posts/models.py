import uuid

from django.db import models
from timescale.db.models import fields as timescale_models
from timescale.db.models.managers import TimescaleManager


class Post(models.Model):
    post_uuid = models.UUIDField(
        default=uuid.uuid4, unique=True, verbose_name="게시글 UUID"
    )
    user = models.ForeignKey(
        to="users.User",
        related_name="posts",
        on_delete=models.CASCADE,
        verbose_name="사용자",
    )
    title = models.CharField(max_length=255, verbose_name="제목")
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="생성 일시"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    def __str__(self):
        return f"{self.post_uuid}"

    class Meta:
        verbose_name = "게시글"
        verbose_name_plural = "게시글 목록"


class PostStatistics(models.Model):
    post = models.OneToOneField(
        to="Post",
        related_name="statistics",
        on_delete=models.CASCADE,
        verbose_name="게시글",
    )
    view_count = models.PositiveIntegerField(
        default=0, verbose_name="전체 조회수"
    )
    like_count = models.PositiveIntegerField(
        default=0, verbose_name="전체 좋아요 수"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="생성 일시"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    def __str__(self):
        return f"{self.post.post_uuid}"

    class Meta:
        verbose_name = "게시글 전체 통계"
        verbose_name_plural = "게시글 전체 통계 목록"


class PostDailyStatistics(models.Model):
    post = models.ForeignKey(
        "Post",
        related_name="daily_statistics",
        on_delete=models.CASCADE,
        verbose_name="게시글",
    )
    date = timescale_models.TimescaleDateTimeField(
        interval="1 day", verbose_name="날짜"
    )
    daily_view_count = models.PositiveIntegerField(
        default=0, verbose_name="일별 조회수"
    )
    daily_like_count = models.PositiveIntegerField(
        default=0, verbose_name="일별 좋아요 수"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="생성 일시"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    objects = models.Manager()
    timescale = TimescaleManager()

    def __str__(self):
        return f"{self.post.post_uuid}"

    class Meta:
        verbose_name = "게시글 일별 통계"
        verbose_name_plural = "게시글 일별 통계 목록"
        unique_together = ("post", "date")
