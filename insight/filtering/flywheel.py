from insight.models import LABEL_DECISION_CHOICES, FilterLabel
from modules.noti.slack_client import notify_ops

ALLOWED_LABEL_DECISIONS = frozenset(
    value for value, _ in LABEL_DECISION_CHOICES
)


def record_label(
    slug: str,
    decision: str,
    score: float = 0.0,
    reason: str = "",
    decided_by: str = "",
) -> FilterLabel:
    """사람 게이트 결정/판명을 라벨로 저장한다(audit + 플라이휠 시드).

    audit·플라이휠 시드로 쓰이므로 저장 시점에 오염 값을 차단한다.
    """
    if not slug.strip():
        raise ValueError("slug 는 비어 있을 수 없습니다.")
    if decision not in ALLOWED_LABEL_DECISIONS:
        raise ValueError(f"지원하지 않는 decision 값입니다: {decision}")

    return FilterLabel.objects.create(
        slug=slug,
        decision=decision,
        score=score,
        reason=reason,
        decided_by=decided_by,
    )


def alert_escaped_spam(escaped_count: int) -> bool:
    """필터를 통과한 스팸이 1건이라도 판명되면 즉시 운영 Slack 알람.

    저볼륨 도메인의 단일 최중요 지표(통계 드리프트 대신 escaped 0건 감시).
    """
    if escaped_count <= 0:
        return False
    return notify_ops(
        f"🚨 광고 필터를 통과한 스팸 {escaped_count}건 발견 — 렉시콘/임계 점검 필요",
        cooldown_key="escaped_spam",
    )
