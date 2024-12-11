from django.db import models
from timescale.db.models import fields as timescale_models
from timescale.db.models.managers import TimescaleManager

from common.models import TimeStampedModel


class Post(TimeStampedModel):
    """
    게시글 모델
    """

    post_uuid = models.UUIDField(
        blank=False, null=False, unique=True, verbose_name="게시글 UUID"
    )
    user = models.ForeignKey(
        to="users.User",
        related_name="posts",
        on_delete=models.CASCADE,
        verbose_name="사용자",
    )
    title = models.CharField(
        blank=False, null=False, max_length=255, verbose_name="제목"
    )

    def __str__(self) -> str:
        return f"{self.post_uuid}"

    class Meta:
        verbose_name = "게시글"
        verbose_name_plural = "게시글 목록"


class PostStatistics(TimeStampedModel):
    """
    게시글 전체 통계 모델
    """

    post = models.OneToOneField(
        to="Post",
        related_name="statistics",
        on_delete=models.CASCADE,
        verbose_name="게시글",
    )
    view_count = models.PositiveIntegerField(
        blank=False, null=False, default=0, verbose_name="전체 조회수"
    )
    like_count = models.PositiveIntegerField(
        blank=False, null=False, default=0, verbose_name="전체 좋아요 수"
    )

    def __str__(self) -> str:
        return f"{self.post.post_uuid}"

    class Meta:
        verbose_name = "게시글 전체 통계"
        verbose_name_plural = "게시글 전체 통계 목록"


class PostDailyStatistics(TimeStampedModel):
    """
    게시글 일별 통계 모델
    """

    post = models.ForeignKey(
        "Post",
        related_name="daily_statistics",
        on_delete=models.CASCADE,
        verbose_name="게시글",
    )
    date = timescale_models.TimescaleDateTimeField(
        blank=False,
        null=False,
        interval="1 day",
        verbose_name="날짜",
    )
    daily_view_count = models.PositiveIntegerField(
        blank=False,
        null=False,
        default=0,
        verbose_name="일별 조회수",
    )
    daily_like_count = models.PositiveIntegerField(
        blank=False,
        null=False,
        default=0,
        verbose_name="일별 좋아요 수",
    )

    objects = models.Manager()
    timescale = TimescaleManager()

    def __str__(self) -> str:
        return f"{self.post.post_uuid}"

    class Meta:
        verbose_name = "게시글 일별 통계"
        verbose_name_plural = "게시글 일별 통계 목록"
