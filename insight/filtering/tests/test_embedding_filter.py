from unittest.mock import MagicMock

from insight.filtering import embedding_filter as ef
from insight.filtering.schemas import VERDICT_DROP, FilterVerdict
from modules.llm.exceptions import GenerationError

REFERENCES = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


def test_ontopic_distance_flags_offtopic():
    """정상 dev 참조셋에 가까우면 거리가 낮고, 멀면(오프토픽) 높다."""
    assert ef.ontopic_distance([1.0, 0.0, 0.0], REFERENCES) < 0.1
    assert ef.ontopic_distance([0.0, 0.0, 1.0], REFERENCES) > 0.9


def test_find_near_duplicates_within_batch():
    """거의 동일한 본문 임베딩 쌍을 다계정 양산으로 검출한다."""
    embeddings = [[1.0, 0.0], [0.999, 0.001], [0.0, 1.0]]
    assert ef.find_near_duplicates(embeddings) == [(0, 1)]


def test_embedding_score_fuses_into_verdict():
    """오프토픽 거리가 크면 휴리스틱 판정 점수에 가산되어 격상된다."""
    base = FilterVerdict(verdict="borderline", score=0.4, triggered_signals=[])
    fused = ef.fuse_embedding_signal(base, distance=0.9)
    assert fused.score > base.score
    assert fused.verdict == VERDICT_DROP


def test_embed_texts_returns_none_on_failure():
    """임베딩 API 실패 시 None 을 반환해 휴리스틱 단독 폴백을 가능케 한다."""
    client = MagicMock()
    client.generate_embedding.side_effect = GenerationError("api down")
    assert ef.embed_texts(client, ["a", "b"]) is None
