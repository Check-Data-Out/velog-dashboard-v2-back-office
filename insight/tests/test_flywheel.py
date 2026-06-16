from unittest.mock import patch

from insight.filtering import flywheel
from insight.models import LABEL_REJECTED, FilterLabel


def test_record_label_persists_gate_decision(db):
    """사람 게이트 결정이 FilterLabel 로 저장된다(audit·플라이휠 시드)."""
    label = flywheel.record_label(
        slug="spam-post",
        decision=LABEL_REJECTED,
        score=0.9,
        reason="gambling",
        decided_by="admin",
    )

    assert FilterLabel.objects.filter(slug="spam-post").exists()
    assert label.decision == LABEL_REJECTED


def test_alert_escaped_spam_notifies_when_positive():
    """escaped 스팸이 1건 이상이면 Slack 알람을 보낸다."""
    with patch.object(
        flywheel, "notify_ops", return_value=True
    ) as mock_notify:
        assert flywheel.alert_escaped_spam(2) is True
        mock_notify.assert_called_once()


def test_alert_escaped_spam_skips_when_zero():
    """escaped 0건이면 알람하지 않는다."""
    with patch.object(flywheel, "notify_ops") as mock_notify:
        assert flywheel.alert_escaped_spam(0) is False
        mock_notify.assert_not_called()
