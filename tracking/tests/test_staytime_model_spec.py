from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from tracking.models import UserStayTime
from users.models import User


class UserEventTrackingTest(TestCase):
    """UserStayTime 모델 테스트"""

    def setUp(self):
        """테스트를 위한 기본 데이터 설정"""
        self.user = User.objects.create(
            velog_uuid="01234567-0123-0123-0123-012345678901",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="a@b.com",
        )

    def test_valid_stay_time(self):
        """
        정상적인 진입 및 퇴출 시간 설정 시 stay_duration 계산 확인
        """
        loaded_at = timezone.now()
        unloaded_at = loaded_at + timedelta(minutes=30)

        stay_time = UserStayTime.objects.create(
            user=self.user,
            loaded_at=loaded_at,
            unloaded_at=unloaded_at,
        )

        self.assertEqual(stay_time.stay_duration, timedelta(minutes=30))

    def test_invalid_unloaded_at_before_loaded_at(self):
        """
        unloaded_at이 loaded_at보다 이전인 경우 ValidationError 발생 확인
        """
        loaded_at = timezone.now()
        unloaded_at = loaded_at - timedelta(minutes=10)

        stay_time = UserStayTime(
            user=self.user,
            loaded_at=loaded_at,
            unloaded_at=unloaded_at,
        )

        with self.assertRaises(ValidationError):
            stay_time.clean()

    def test_str_method(self):
        """
        __str__ 메서드가 기대하는 문자열 형식으로 반환되는지 확인
        """
        loaded_at = timezone.now()
        unloaded_at = loaded_at + timedelta(minutes=15)

        stay_time = UserStayTime.objects.create(
            user=self.user,
            loaded_at=loaded_at,
            unloaded_at=unloaded_at,
        )

        expected_str = f"{self.user.email} - 0:15:00 체류"
        self.assertEqual(str(stay_time), expected_str)

    def test_missing_loaded_at_raises_error(self):
        """
        loaded_at 필드가 명시되지 않으면 IntegrityError 발생 확인
        """
        with self.assertRaises(Exception):
            UserStayTime.objects.create(
                user=self.user,
                unloaded_at=timezone.now() + timedelta(minutes=20),
            )

    def test_missing_unloaded_at_raises_error(self):
        """
        unloaded_at 필드가 명시되지 않으면 IntegrityError 발생 확인
        """
        with self.assertRaises(Exception):
            UserStayTime.objects.create(
                user=self.user,
                loaded_at=timezone.now(),
            )
