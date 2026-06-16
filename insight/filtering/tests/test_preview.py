from insight.filtering.preview import build_filter_preview
from insight.filtering.schemas import (
    VERDICT_DROP,
    VERDICT_PASS,
    FilterVerdict,
)


def test_build_filter_preview_shows_verdict_and_reasons():
    """프리뷰에 판정·점수·사유·URL 이 사람 검수용으로 노출된다."""
    candidates = [
        {
            "title": "노래방 도우미 급구",
            "username": "spammer",
            "slug": "ad",
            "verdict": FilterVerdict(
                verdict=VERDICT_DROP,
                score=1.0,
                category="adult",
                triggered_signals=["adult:노래방도우미", "offtopic"],
            ),
        },
        {
            "title": "리액트 서버 컴포넌트",
            "username": "dev",
            "slug": "rsc",
            "verdict": FilterVerdict(verdict=VERDICT_PASS, score=0.0),
        },
    ]

    preview = build_filter_preview(candidates)

    assert "🚫" in preview
    assert "노래방 도우미 급구" in preview
    assert "adult:노래방도우미" in preview
    assert "https://velog.io/@dev/rsc" in preview


def test_build_filter_preview_empty():
    """후보가 없으면 빈 문자열."""
    assert build_filter_preview([]) == ""
