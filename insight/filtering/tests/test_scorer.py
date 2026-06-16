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
        ("부담없이 문의주세요 01012345678 상담", []),  # 오프토픽 + 연락처
        (
            "자세한 내용은 본문을 참고하세요",
            ["온라인카지노"],
        ),  # 오프토픽 + 태그
    ],
)
def test_hard_rule_offtopic_branches_drop(body, tags):
    """오프토픽 + (연락처 | 오프토픽 태그) → drop."""
    assert score_post(body=body, title="", tags=tags).verdict == VERDICT_DROP


@pytest.mark.parametrize(
    "body",
    [
        "이웃집 토토로를 다시 봤어요. 정말 명작입니다.",  # 토토 오탐 방지
        "드디어 학자금 대출 다 갚았습니다 후련하네요",  # 약신호 단독 오탐 방지
        "Vue 슬롯 컴포넌트 구현 방법을 정리했습니다",  # 슬롯 오탐 + dev
    ],
)
def test_normal_post_not_dropped(body):
    """일반어/정상 개인글이 substring·약신호로 잘못 drop 되지 않는다(FP 회귀)."""
    assert score_post(body=body, title="", tags=[]).verdict != VERDICT_DROP


def test_disguised_loan_recruit_spam_drops():
    """dev 태그로 위장해도 다중 약신호+오프토픽이면 soft score 로 drop 된다."""
    body = "무담보대출 작업대출 당일지급 고수익부업 지금 신청"
    verdict = score_post(body=body, title="", tags=["python", "react"])
    assert verdict.verdict == VERDICT_DROP


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
