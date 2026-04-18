"""users/admin.update_stats 큐 기반 동작 테스트.

동기 ScraperTargetUser 호출 제거 확인 + 중복 요청 가드 + lifecycle 기록.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from ops_tracking.models import StatsRefreshRequest, StatsRefreshRequestStatus
from ops_tracking.services import RequestLifecycleService
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(db):
    U = get_user_model()
    return U.objects.create_user(
        username="ops", password="p@ssw0rd", is_staff=True, is_superuser=True
    )


@pytest.fixture
def target_users(db):
    return [
        User.objects.create(
            velog_uuid=uuid.uuid4(),
            access_token="t",
            refresh_token="t",
            group_id=1,
            email=f"t-{i}@ex.com",
            username=f"t-{i}",
            is_active=True,
        )
        for i in range(3)
    ]


@pytest.fixture(autouse=True)
def stub_redis():
    """RedisQueueClient 싱글톤을 stub 으로 교체하여 실제 Redis 연결 회피."""
    with patch("users.admin.QueueMonitorService") as mock_service_cls:
        service = MagicMock()
        service.redis_client = MagicMock()
        service.redis_client.enqueue_message = MagicMock()
        mock_service_cls.return_value = service
        yield service


def _trigger_action(superuser, users):
    """UserAdmin.update_stats 를 request 객체와 함께 직접 호출."""
    from django.contrib.admin.sites import AdminSite

    from users.admin import UserAdmin
    from users.models import User as UserModel

    admin_instance = UserAdmin(UserModel, AdminSite())
    factory = RequestFactory()
    request = factory.post("/admin/users/user/")
    request.user = superuser
    admin_instance.message_user = MagicMock()
    qs = UserModel.objects.filter(pk__in=[u.pk for u in users])
    admin_instance.update_stats(request, qs)
    return admin_instance


class TestUpdateStats:
    def test_enqueues_one_message_and_one_tracking_row_per_user(
        self, superuser, target_users, stub_redis
    ):
        admin_instance = _trigger_action(superuser, target_users)
        assert stub_redis.redis_client.enqueue_message.call_count == 3
        assert StatsRefreshRequest.objects.count() == 3
        # 모두 QUEUED 상태
        assert all(
            r.status == StatsRefreshRequestStatus.QUEUED
            for r in StatsRefreshRequest.objects.all()
        )
        # requested_by 는 auth.User email 이 users.User 에 없으면 None
        assert all(
            r.requested_by_id is None
            for r in StatsRefreshRequest.objects.all()
        )
        admin_instance.message_user.assert_called_once()

    def test_rejects_selection_over_limit(self, superuser, db, stub_redis):
        users = [
            User.objects.create(
                velog_uuid=uuid.uuid4(),
                access_token="t",
                refresh_token="t",
                group_id=1,
                email=f"over-{i}@ex.com",
                username=f"over-{i}",
                is_active=True,
            )
            for i in range(11)
        ]
        admin_instance = _trigger_action(superuser, users)
        # 큐잉 실행 안 됨
        stub_redis.redis_client.enqueue_message.assert_not_called()
        assert StatsRefreshRequest.objects.count() == 0
        # ERROR 메시지
        call_args = admin_instance.message_user.call_args
        assert call_args[0][2] is not None  # messages.ERROR

    def test_skips_users_with_inflight_request(
        self, superuser, target_users, stub_redis
    ):
        # target_users[0] 에 이미 QUEUED 상태 기록 (requested_by 는 None)
        lifecycle = RequestLifecycleService()
        lifecycle.mark_queued(str(uuid.uuid4()), target_users[0].id, None)
        _trigger_action(superuser, target_users)
        # 3명 중 1명은 스킵 → 2번만 큐잉
        assert stub_redis.redis_client.enqueue_message.call_count == 2
        # 기존 1건 + 신규 2건 = 3
        assert StatsRefreshRequest.objects.count() == 3

    def test_does_not_call_scraper_target_user_sync(
        self, superuser, target_users, stub_redis
    ):
        # ScraperTargetUser 가 users.admin 모듈에서 더이상 import 되지 않음을 검증
        import users.admin as admin_module

        assert not hasattr(admin_module, "ScraperTargetUser")
        assert not hasattr(admin_module, "async_to_sync")

    def test_enqueue_failure_marks_error_level(
        self, superuser, target_users, stub_redis
    ):
        """리뷰: Redis enqueue 실패를 skip 이 아닌 에러로 표시."""
        from django.contrib import messages as django_messages

        stub_redis.redis_client.enqueue_message.side_effect = Exception(
            "redis down"
        )
        admin_instance = _trigger_action(superuser, target_users)
        # failed 카운트가 있으면 message level = ERROR
        call_args = admin_instance.message_user.call_args
        msg_text, level = call_args[0][1], call_args[0][2]
        assert "Redis enqueue 실패" in msg_text
        assert level == django_messages.ERROR
        # 고아 행 없음 — 실패 시 삭제되어야 함
        assert StatsRefreshRequest.objects.count() == 0
