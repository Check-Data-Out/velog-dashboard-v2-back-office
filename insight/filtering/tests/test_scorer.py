import pytest

from insight.filtering.schemas import (
    VERDICT_BORDERLINE,
    VERDICT_DROP,
    VERDICT_PASS,
)
from insight.filtering.scorer import score_post


def test_hard_rule_adult_gambling_drug_drops():
    """유흥/도박/약물 렉시콘은 단독으로도 drop 된다."""
    verdict = score_post(
        body="노래방 도우미 급구 010-1234-5678", title="", tags=[]
    )
    assert verdict.verdict == VERDICT_DROP
    assert verdict.category == "adult"


@pytest.mark.parametrize(
    "body, tags",
    [
        ("부담없이 문의주세요 01012345678 상담", []),  # 연락처
        ("대출 한도 무담보로 가능합니다", []),  # 약신호 렉시콘
        ("자세한 내용은 본문을 참고하세요", ["대출"]),  # 오프토픽 태그
    ],
)
def test_hard_rule_offtopic_branches_drop(body, tags):
    """오프토픽 + (연락처 | 약신호 렉시콘 | 오프토픽 태그) → drop."""
    assert score_post(body=body, title="", tags=tags).verdict == VERDICT_DROP


def test_dev_related_self_promo_passes():
    """개발 관련 자기홍보는 연락처가 있어도 통과한다(정책)."""
    body = (
        "제가 만든 서비스입니다. 리액트 서버 배포 api 도커로 구현했어요. "
        "문의는 카톡 주세요"
    )
    verdict = score_post(
        body=body, title="사이드프로젝트 공유", tags=["react"]
    )
    assert verdict.verdict == VERDICT_PASS


def test_recruit_lexicon_alone_with_dev_not_dropped():
    """모집 렉시콘 단독 + 개발 관련 글은 drop 되지 않는다(커리어 보호)."""
    body = "고수익 부업 후기. 리액트 서버 배포 api 도커 깃 테스트 자동화"
    assert (
        score_post(body=body, title="", tags=["python"]).verdict
        != VERDICT_DROP
    )


def test_soft_score_borderline_band():
    """오프토픽이지만 보강 신호가 없으면 borderline 으로 분류한다."""
    verdict = score_post(
        body="오늘 날씨가 좋아서 산책을 다녀왔습니다.", title="일상", tags=[]
    )
    assert verdict.verdict == VERDICT_BORDERLINE


def test_verdict_includes_triggered_signals():
    """판정 사유가 triggered_signals 에 담긴다(Slack 프리뷰용)."""
    verdict = score_post(
        body="노래방 도우미 급구 카톡 문의", title="", tags=[]
    )
    assert any("adult" in s for s in verdict.triggered_signals)


def test_empty_body_not_auto_dropped():
    """본문이 비어도 자동 drop 하지 않고 borderline 으로 둔다."""
    assert score_post(body="", title="", tags=[]).verdict != VERDICT_DROP
