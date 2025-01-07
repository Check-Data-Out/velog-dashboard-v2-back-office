from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models

from users.models import User


class UserEventType(models.TextChoices):
    """사용자 이벤트 추적을 위한 이벤트 타입 META"""

    LOGIN = "11", "로그인 성공"  # 로그인 성공
    NAVIGATE = "12", "페이지 이동"  # 페이지 이동 (헤더 클릭 등)
    LOGOUT = "13", "로그아웃"  # 로그아웃
    SECTION_INTERACT_MAIN = (
        "21",
        "메인(통계 블록 열림/닫힘)",
    )  # 메인 페이지 - 통계 블록 열림/닫힘
    SORT_INTERACT_MAIN = (
        "22",
        "메인(정렬 선택)",
    )  # 메인 페이지 - 정렬(오름차순, 방식) 선택
    REFRESH_INTERACT_MAIN = (
        "23",
        "메인(새로고침)",
    )  # 메인 페이지 - 새로고침 버튼
    SORT_INTERACT_BOARD = (
        "31",
        "리더보드(정렬 선택)",
    )  # 리더보드 페이지 - 정렬 방식 선택

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
    request_header = models.JSONField(
        null=False,
        blank=False,
        default=dict,
        verbose_name="요청 헤더",
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

    @property
    def stay_duration(self) -> timedelta:
        if self.unloaded_at and self.loaded_at:
            return self.unloaded_at - self.loaded_at
        return timedelta(0)

    def clean(self):
        if (
            self.unloaded_at
            and self.loaded_at
            and self.unloaded_at < self.loaded_at
        ):
            raise ValidationError(
                "퇴출 일시는 진입 일시보다 나중이어야 합니다."
            )

    def __str__(self):
        return f"{self.user.email} - {self.stay_duration} 체류"

    class Meta:
        verbose_name = "사용자 체류시간"
        verbose_name_plural = "사용자 체류시간 목록"
