from dataclasses import dataclass, field

from common.models import SerializableMixin

VERDICT_DROP = "drop"
VERDICT_PASS = "pass"
VERDICT_BORDERLINE = "borderline"


@dataclass
class SignalResult(SerializableMixin):
    """단일 휴리스틱/임베딩 신호의 산출."""

    name: str = ""
    score: float = 0.0
    matched: list[str] = field(default_factory=list)


@dataclass
class FilterVerdict(SerializableMixin):
    """글 1개에 대한 필터 판정. triggered_signals 는 Slack 프리뷰에 노출된다."""

    verdict: str = VERDICT_PASS
    score: float = 0.0
    category: str = ""
    triggered_signals: list[str] = field(default_factory=list)


@dataclass
class FilterLabel(SerializableMixin):
    """사람 게이트 결정/escaped 판명을 라벨로 누적(플라이휠)."""

    slug: str = ""
    decision: str = ""
    score: float = 0.0
    reason: str = ""
