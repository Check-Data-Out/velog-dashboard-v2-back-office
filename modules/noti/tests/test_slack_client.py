"""Slack client 테스트 (webhook mock + cooldown)."""

from unittest.mock import MagicMock, patch

from modules.noti import slack_client


class TestNotifyOpsEnv:
    def test_no_op_when_webhook_env_missing(self, monkeypatch):
        monkeypatch.setenv("SLACK_OPS_WEBHOOK", "")
        assert slack_client.notify_ops("hi") is False


class TestNotifyOpsPosting:
    def test_posts_to_webhook_once(self, monkeypatch):
        monkeypatch.setenv("SLACK_OPS_WEBHOOK", "https://hooks/slack/test")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch(
            "modules.noti.slack_client.urlrequest.urlopen",
            return_value=mock_resp,
        ) as mock_open:
            ok = slack_client.notify_ops("hello ops")
        assert ok is True
        assert mock_open.call_count == 1
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://hooks/slack/test"

    def test_returns_false_on_non_2xx(self, monkeypatch):
        monkeypatch.setenv("SLACK_OPS_WEBHOOK", "https://hooks/slack/test")
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch(
            "modules.noti.slack_client.urlrequest.urlopen",
            return_value=mock_resp,
        ):
            assert slack_client.notify_ops("hello") is False


class TestHttpsValidation:
    def test_rejects_non_https_webhook(self, monkeypatch):
        """리뷰: HTTPS 이외 scheme 은 운영 실수 방지 차원에서 거부."""
        monkeypatch.setenv("SLACK_OPS_WEBHOOK", "http://hooks/slack/test")
        with patch(
            "modules.noti.slack_client.urlrequest.urlopen"
        ) as mock_open:
            assert slack_client.notify_ops("hi") is False
        mock_open.assert_not_called()


class TestCooldown:
    def test_respects_cooldown_when_redis_returns_existing_key(
        self, monkeypatch
    ):
        monkeypatch.setenv("SLACK_OPS_WEBHOOK", "https://hooks/slack/test")
        redis_mock = MagicMock()
        # SET NX 가 None 반환 → 이미 cooldown 존재
        redis_mock.client.set.return_value = None
        with patch(
            "modules.noti.slack_client.urlrequest.urlopen"
        ) as mock_open:
            sent = slack_client.notify_ops(
                "hi", cooldown_key="missing-posts", redis_client=redis_mock
            )
        assert sent is False
        mock_open.assert_not_called()

    def test_releases_cooldown_on_send_failure(self, monkeypatch):
        """리뷰: 전송 실패 후 30분 묵살 방지 — cooldown 키 삭제."""
        monkeypatch.setenv("SLACK_OPS_WEBHOOK", "https://hooks/slack/test")
        redis_mock = MagicMock()
        redis_mock.client.set.return_value = True  # cooldown 획득 성공
        with patch(
            "modules.noti.slack_client.urlrequest.urlopen",
            side_effect=Exception("network"),
        ):
            sent = slack_client.notify_ops(
                "hi", cooldown_key="k1", redis_client=redis_mock
            )
        assert sent is False
        redis_mock.client.delete.assert_called_once_with(
            "vd2:ops:slack:cooldown:k1"
        )

    def test_sends_when_cooldown_key_newly_acquired(self, monkeypatch):
        monkeypatch.setenv("SLACK_OPS_WEBHOOK", "https://hooks/slack/test")
        redis_mock = MagicMock()
        redis_mock.client.set.return_value = True  # NX 성공
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch(
            "modules.noti.slack_client.urlrequest.urlopen",
            return_value=mock_resp,
        ) as mock_open:
            sent = slack_client.notify_ops(
                "hi", cooldown_key="k1", redis_client=redis_mock
            )
        assert sent is True
        mock_open.assert_called_once()
