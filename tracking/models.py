from django.db import models

from users.models import User


class UserEventType(models.TextChoices):
    """사용자 이벤트 추적을 위한 이벤트 타입 META"""

    LOGIN = "01", "로그인"  # 사용자 로그인 이벤트
    POST_CLICK = "02", "포스트 클릭"  # 포스트 클릭 이벤트
    POST_GRAPH_CLICK = "03", "포스트 그래프 클릭"  # 포스트 그래프 클릭 이벤트
    EXIT = "04", "종료"  # 종료 이벤트
    NOTHING = "99", "nothing"  # 디폴트 값, 또는 임의 부여 값


class UserEventTracking(models.Model):
    """
    사용자 이벤트 추적을 위한 모델
    """

    event_type = models.CharField(
        max_length=2,
        blank=False,
        null=False,
        default=UserEventType.NOTHING,
        choices=UserEventType.choices,
        help_text="어떤 이벤트 타입인지 저장하는 필드입니다.",
        verbose_name="이벤트타입",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="event_tracks",
        verbose_name="사용자",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성 일시",
    )

    def __str__(self):
        return f"{self.user.email} - {self.event_type} at {self.created_at}"

    class Meta:
        verbose_name = "사용자 이벤트"
        verbose_name_plural = "사용자 이벤트 목록"


class UserStayTime(models.Model):
    """
    사용자 체류시간 추적을 위한 모델
    """

    loaded_at = models.DateTimeField(verbose_name="진입 일시")
    unloaded_at = models.DateTimeField(verbose_name="퇴출 일시")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="event_staytimes",
        verbose_name="사용자",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성 일시",
    )

    def __str__(self):
        return f"{self.user.email} - {self.unloaded_at - self.loaded_at} 체류"

    class Meta:
        verbose_name = "사용자 체류시간"
        verbose_name_plural = "사용자 체류시간 목록"
