from django.test import TestCase

from tracking.models import UserEventTracking, UserEventType
from users.models import User


class UserEventTrackingTest(TestCase):
    """UserEventTracking 모델 테스트"""

    def setUp(self):
        """테스트를 위한 기본 데이터 설정"""
        self.user = User.objects.create(
            velog_uuid="01234567-0123-0123-0123-012345678901",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            group_id=1,
            email="a@b.com",
        )

    def test_create_event_tracking(self):
        """트래킹 이벤트 생성 테스트"""
        event = UserEventTracking.objects.create(
            user=self.user, event_type=UserEventType.LOGIN
        )
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.event_type, UserEventType.LOGIN)
        self.assertIsNotNone(event.created_at)

    def test_event_type_choices(self):
        """트래킹 이벤트 타입 선택 테스트"""
        event_types = [
            UserEventType.LOGIN,
            UserEventType.NAVIGATE,
            UserEventType.LOGOUT,
            UserEventType.SECTION_INTERACT_MAIN,
            UserEventType.SORT_INTERACT_MAIN,
            UserEventType.REFRESH_INTERACT_MAIN,
            UserEventType.SORT_INTERACT_BOARD,
            UserEventType.NOTHING,
        ]

        for event_type in event_types:
            event = UserEventTracking.objects.create(
                user=self.user, event_type=event_type
            )
            self.assertEqual(event.event_type, event_type)

    def test_default_event_type(self):
        """트래킹, 기본 이벤트 타입 테스트"""
        event = UserEventTracking.objects.create(user=self.user)
        self.assertEqual(event.event_type, UserEventType.NOTHING)

    def test_str_representation(self):
        """트래킹, 문자열 표현 테스트"""
        event = UserEventTracking.objects.create(
            user=self.user, event_type=UserEventType.LOGIN
        )
        expected_str = (
            f"{self.user.email} - {UserEventType.LOGIN} at {event.created_at}"
        )
        self.assertEqual(str(event), expected_str)
