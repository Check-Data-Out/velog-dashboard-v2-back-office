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
        ]
        assert all(field in list_display for field in expected_fields)

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
