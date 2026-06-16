import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도. 빈 벡터나 영벡터는 0.0."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def max_cosine_similarity(
    vector: list[float], references: list[list[float]]
) -> float:
    """참조 벡터 집합 중 최대 코사인 유사도 (kNN/few-shot 거리용)."""
    return max(
        (cosine_similarity(vector, ref) for ref in references), default=0.0
    )
