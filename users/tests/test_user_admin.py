import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    @patch("users.admin.ScraperTargetUser")
    def test_update_stats_success(
        self, mock_scraper, user_admin, user, request_with_messages
    ):
        mock_scraper_instance = MagicMock()
        mock_scraper.return_value = mock_scraper_instance
        mock_scraper_instance.run = AsyncMock()

        queryset = User.objects.filter(pk=user.pk)
        user_admin.update_stats(request_with_messages, queryset)

        # Scraper 호출 확인
        mock_scraper.assert_called_once_with([user.pk])
        mock_scraper_instance.run.assert_called_once()

        # 메시지 확인
        messages_list = [m.message for m in request_with_messages._messages]
        assert (
            "1 명의 사용자 통계를 실시간 업데이트 성공했습니다."
            in messages_list
        )

    @patch("users.admin.ScraperTargetUser")
    def test_update_stats_failure(
        self, mock_scraper, user_admin, user, request_with_messages
    ):
        mock_scraper_instance = MagicMock()
        mock_scraper.return_value = mock_scraper_instance
        mock_scraper_instance.run = AsyncMock(
            side_effect=Exception("Test error")
        )

        queryset = User.objects.filter(pk=user.pk)
        user_admin.update_stats(request_with_messages, queryset)

        # 메시지 확인 (에러 발생 시)
        messages_list = [m.message for m in request_with_messages._messages]
        assert any(
            "실시간 통계 업데이트를 실패했습니다" in msg
            for msg in messages_list
        )

    @patch("users.admin.ScraperTargetUser")
    def test_update_stats_more_than_three_users(
        self, mock_scraper, user_admin, request_with_messages
    ):
        users = [
            User.objects.create(
                velog_uuid=uuid.uuid4(),
                access_token=f"test-token-{i}",
                refresh_token=f"test-refresh-token-{i}",
                group_id=i,
                email=f"user{i}@example.com",
                is_active=True,
            )
            for i in range(3)
        ]

        queryset = User.objects.filter(pk__in=[user.pk for user in users])
        user_admin.update_stats(request_with_messages, queryset)

        # Scraper가 호출되지 않았는지 확인
        mock_scraper.assert_not_called()

        # 메시지 확인 (3명 초과 선택 시 오류)
        messages_list = [m.message for m in request_with_messages._messages]
        assert any(
            "3명 이상의 유저를 선택하지 말아주세요" in msg
            for msg in messages_list
        )
