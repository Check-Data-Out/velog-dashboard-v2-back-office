import json
from unittest.mock import MagicMock

from insight.filtering import pipeline
from insight.filtering.schemas import VERDICT_DROP


def test_classify_post_heuristic_drops_offtopic_ad():
    """클라이언트 없이 휴리스틱만으로 오프토픽 광고를 drop 한다."""
    verdict = pipeline.classify_post(
        body="노래방 도우미 급구 010-1234-5678", title="광고", tags=[]
    )
    assert verdict.verdict == VERDICT_DROP


def test_classify_post_skips_llm_when_not_borderline():
    """확정(drop/pass) 글은 LLM 을 호출하지 않는다(비용 절감)."""
    llm = MagicMock()
    pipeline.classify_post(
        body="노래방 도우미 급구", title="광고", tags=[], llm_client=llm
    )
    llm.generate_text.assert_not_called()


def test_classify_post_invokes_llm_on_borderline():
    """borderline 글은 LLM 보조 판정을 호출해 확정한다."""
    llm = MagicMock()
    llm.generate_text.return_value = json.dumps(
        {"is_spam": True, "category": "gambling", "reason": "x"}
    )
    verdict = pipeline.classify_post(
        body="오늘 날씨가 좋아서 산책을 했습니다",
        title="일상",
        tags=[],
        llm_client=llm,
    )
    llm.generate_text.assert_called()
    assert verdict.verdict == VERDICT_DROP
