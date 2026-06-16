import logging

from insight.filtering.constants import (
    EMBEDDING_OFFTOPIC_WEIGHT,
    NEAR_DUP_THRESHOLD,
    ONTOPIC_DISTANCE_THRESHOLD,
    SPAM_SCORE_DROP_THRESHOLD,
    SPAM_SCORE_PASS_THRESHOLD,
)
from insight.filtering.schemas import (
    VERDICT_BORDERLINE,
    VERDICT_DROP,
    VERDICT_PASS,
    FilterVerdict,
)
from modules.content_filter.distance import (
    cosine_similarity,
    max_cosine_similarity,
)
from modules.llm.exceptions import GenerationError

logger = logging.getLogger("newsletter")


def ontopic_distance(
    embedding: list[float], reference_embeddings: list[list[float]]
) -> float:
    """큐레이팅한 정상 dev 글 참조셋과의 거리(1 - 최대 코사인). 높을수록 오프토픽."""
    if not reference_embeddings:
        return 0.0
    return 1.0 - max_cosine_similarity(embedding, reference_embeddings)


def find_near_duplicates(
    embeddings: list[list[float]], threshold: float = NEAR_DUP_THRESHOLD
) -> list[tuple[int, int]]:
    """배치 내 거의 동일한 본문 쌍(다계정 양산 스팸)을 검출한다."""
    pairs = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            if cosine_similarity(embeddings[i], embeddings[j]) >= threshold:
                pairs.append((i, j))
    return pairs


def embed_texts(client, texts: list[str]) -> list[list[float]] | None:
    """임베딩 일괄 생성. 실패 시 None 을 반환해 휴리스틱 단독으로 폴백한다."""
    try:
        result = client.generate_embedding(texts)
        if result and isinstance(result[0], float):
            return [result]  # 단일 입력 방어
        return result
    except GenerationError as e:
        logger.warning(
            "Embedding failed, falling back to heuristic-only: %s", e
        )
        return None


def fuse_embedding_signal(
    verdict: FilterVerdict,
    distance: float,
    threshold: float = ONTOPIC_DISTANCE_THRESHOLD,
) -> FilterVerdict:
    """온토픽 거리를 휴리스틱 판정에 가산. 임계 미만이면 그대로 둔다."""
    if distance < threshold:
        return verdict

    score = min(1.0, verdict.score + EMBEDDING_OFFTOPIC_WEIGHT)
    if score >= SPAM_SCORE_DROP_THRESHOLD:
        new_verdict = VERDICT_DROP
    elif score <= SPAM_SCORE_PASS_THRESHOLD:
        new_verdict = VERDICT_PASS
    else:
        new_verdict = VERDICT_BORDERLINE

    return FilterVerdict(
        verdict=new_verdict,
        score=round(score, 3),
        category=verdict.category,
        triggered_signals=verdict.triggered_signals
        + [f"embedding_offtopic:{round(distance, 3)}"],
    )
