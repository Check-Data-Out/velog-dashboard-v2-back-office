import logging

from insight.filtering.embedding_filter import (
    fuse_embedding_signal,
    ontopic_distance,
)
from insight.filtering.llm_judge import judge_borderline
from insight.filtering.schemas import VERDICT_BORDERLINE, FilterVerdict
from insight.filtering.scorer import score_post

logger = logging.getLogger("newsletter")


def classify_post(
    body: str,
    title: str,
    tags: list[str],
    *,
    embedding: list[float] | None = None,
    reference_embeddings: list[list[float]] | None = None,
    llm_client=None,
) -> FilterVerdict:
    """글 1개를 분류한다. 휴리스틱이 기본, 임베딩/LLM 은 주어질 때만 가산·확정.

    LLM(C)은 borderline 일 때만 호출하여 비용을 절감한다(2-패스).
    """
    verdict = score_post(body, title, tags)

    if embedding is not None and reference_embeddings:
        distance = ontopic_distance(embedding, reference_embeddings)
        verdict = fuse_embedding_signal(verdict, distance)

    if verdict.verdict == VERDICT_BORDERLINE and llm_client is not None:
        verdict = judge_borderline(llm_client, body, title)

    return verdict
