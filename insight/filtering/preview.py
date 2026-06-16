from insight.filtering.schemas import (
    VERDICT_BORDERLINE,
    VERDICT_DROP,
    VERDICT_PASS,
    FilterVerdict,
)

VERDICT_EMOJI = {
    VERDICT_DROP: "🚫",
    VERDICT_BORDERLINE: "⚠️",
    VERDICT_PASS: "✅",
}


def build_filter_preview(candidates: list[dict]) -> str:
    """발송 전 Slack 검수용 후보 프리뷰 텍스트를 만든다.

    각 candidate: {"title", "username", "slug", "verdict": FilterVerdict}.
    사람이 drop/borderline 을 보고 admin 에서 편집할 수 있도록 사유를 노출한다.
    """
    lines = []
    for candidate in candidates:
        verdict: FilterVerdict = candidate["verdict"]
        emoji = VERDICT_EMOJI.get(verdict.verdict, "")
        url = f"https://velog.io/@{candidate['username']}/{candidate['slug']}"
        reasons = ", ".join(verdict.triggered_signals) or "-"
        lines.append(
            f"{emoji} [{verdict.verdict} {verdict.score}] "
            f"{candidate['title']} ({url}) — {reasons}"
        )
    return "\n".join(lines)
