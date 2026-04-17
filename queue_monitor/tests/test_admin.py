"""Phase 3 — Queue Monitor Admin 뷰 테스트.

AdminSite 커스텀 URL (dashboard/failed/retry/purge) 동작과 staff 인증 검증.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


@pytest.fixture
def staff_client(db):
    User = get_user_model()
    user = User.objects.create_user(
        username="ops-staff",
        password="p@ssw0rd",
        is_staff=True,
        is_superuser=True,
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def anon_client():
    return Client()


@pytest.fixture(autouse=True)
def patch_service():
    """RedisQueueClient 연결을 피하도록 QueueMonitorService 를 mock."""
    with patch("queue_monitor.admin.QueueMonitorService") as mock_cls:
        instance = mock_cls.return_value
        instance.get_queue_stats.return_value = {
            "pending": 4,
            "processing": 1,
            "failed": 2,
        }
        instance.get_failed_messages.return_value = [
            {
                "requestId": "rid-1",
                "userId": 10,
                "retryCount": 3,
                "lastAttemptAt": "2026-04-18T00:00:00+09:00",
            }
        ]
        instance.retry_failed_message.return_value = True
        instance.purge_failed.return_value = 2
        yield instance


class TestDashboardView:
    def test_renders_three_counters_for_staff(self, staff_client):
        url = reverse("admin:queue_dashboard")
        resp = staff_client.get(url)
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Pending" in body and "4" in body
        assert "Processing" in body and "1" in body
        assert "Failed" in body and "2" in body

    def test_anonymous_redirects_to_login(self, anon_client):
        url = reverse("admin:queue_dashboard")
        resp = anon_client.get(url)
        assert resp.status_code == 302
        assert "login" in resp["Location"]


class TestFailedListView:
    def test_renders_failed_items(self, staff_client):
        url = reverse("admin:queue_failed_list")
        resp = staff_client.get(url)
        assert resp.status_code == 200
        assert b"rid-1" in resp.content


class TestRetryView:
    def test_get_redirects_without_action(self, staff_client, patch_service):
        url = reverse("admin:queue_retry", args=["rid-1"])
        resp = staff_client.get(url)
        assert resp.status_code == 302
        patch_service.retry_failed_message.assert_not_called()

    def test_post_invokes_service(self, staff_client, patch_service):
        url = reverse("admin:queue_retry", args=["rid-1"])
        resp = staff_client.post(url)
        assert resp.status_code == 302
        patch_service.retry_failed_message.assert_called_once_with("rid-1")


class TestPurgeView:
    def test_get_renders_confirmation_form(self, staff_client, patch_service):
        url = reverse("admin:queue_purge")
        resp = staff_client.get(url)
        assert resp.status_code == 200
        assert "전체 삭제" in resp.content.decode()
        patch_service.purge_failed.assert_not_called()

    def test_post_without_confirm_renders_form_again(
        self, staff_client, patch_service
    ):
        url = reverse("admin:queue_purge")
        resp = staff_client.post(url, data={})
        assert resp.status_code == 200
        patch_service.purge_failed.assert_not_called()

    def test_post_with_confirm_yes_invokes_purge(
        self, staff_client, patch_service
    ):
        url = reverse("admin:queue_purge")
        resp = staff_client.post(url, data={"confirm": "yes"})
        assert resp.status_code == 302
        patch_service.purge_failed.assert_called_once()
