import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User as DjangoUser
from django.http import HttpRequest
from django.urls import reverse

from users.models import User


@pytest.mark.django_db
class TestUserAdmin:
    def test_get_list_display(self, user_admin, request_with_messages):
        list_display = user_admin.get_list_display(request_with_messages)
        expected_fields = [
            "velog_uuid",
            "email",
            "group_id",
            "is_active",
            "created_at",
            "get_qr_login_token",
            "get_qr_expires_at",
            "get_qr_is_used",
        ]
        assert all(field in list_display for field in expected_fields)

    def test_get_qr_login_token(self, user_admin, user, qr_login_token):
        user.prefetched_qr_tokens = [qr_login_token]
        result = user_admin.get_qr_login_token(user)
        assert result == qr_login_token.token

    def test_get_qr_login_token_none(self, user_admin, user):
        user.prefetched_qr_tokens = []
        result = user_admin.get_qr_login_token(user)
        assert result == "-"

    def test_get_qr_expires_at(self, user_admin, user, qr_login_token):
        user.prefetched_qr_tokens = [qr_login_token]
        result = user_admin.get_qr_expires_at(user)
        assert result == qr_login_token.expires_at

    def test_get_qr_is_used(self, user_admin, user, qr_login_token):
        qr_login_token.is_used = True
        qr_login_token.save()

        user.prefetched_qr_tokens = [qr_login_token]
        result = user_admin.get_qr_is_used(user)
        assert "사용" in result

    @patch("users.admin.logger.info")
    def test_make_inactive(
        self, mock_logger, user_admin, user, request_with_messages
    ):
        queryset = User.objects.filter(pk=user.pk)
        user_admin.make_inactive(request_with_messages, queryset)

        # 사용자 비활성화 확인
        user.refresh_from_db()
        assert not user.is_active

        # 메시지 확인
        messages_list = [m.message for m in request_with_messages._messages]
        assert "1 명의 사용자가 비활성화되었습니다." in messages_list

        # 로깅 확인
        mock_logger.assert_called_once()

    @patch("users.admin.logger.info")
    def test_make_inactive_bumps_session_version(
        self, mock_logger, user_admin, user, request_with_messages
    ):
        other = User.objects.create(
            velog_uuid=uuid.uuid4(),
            access_token="other-access-token",
            refresh_token="other-refresh-token",
            group_id=2,
        )

        user_admin.make_inactive(
            request_with_messages, User.objects.filter(pk=user.pk)
        )

        user.refresh_from_db()
        other.refresh_from_db()
        assert user.session_version == 1
        # 선택하지 않은 사용자의 세션은 그대로 둔다
        assert other.session_version == 0

    def test_make_inactive_requires_change_permission(self, user_admin, db):
        viewer = DjangoUser.objects.create_user(
            username="viewer", password="viewerpassword", is_staff=True
        )
        viewer.user_permissions.add(
            Permission.objects.get(
                codename="view_user", content_type__app_label="users"
            )
        )
        request = HttpRequest()
        request.user = viewer

        assert "make_inactive" not in user_admin.get_actions(request)

    def test_change_page_has_no_session_version_input(
        self, client_logged_in, user
    ):
        response = client_logged_in.get(
            reverse("admin:users_user_change", args=[user.pk])
        )

        assert response.status_code == 200
        assert 'name="session_version"' not in response.content.decode()

    # update_stats 동기 경로 테스트는 users/tests/test_admin_update_stats.py 로 이전됨.
