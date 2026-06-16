from modules.content_filter.distance import (
    cosine_similarity,
    max_cosine_similarity,
)


def test_cosine_similarity_identical_vectors():
    """동일 방향 벡터는 유사도 1.0."""
    assert cosine_similarity([1.0, 0.0], [2.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal():
    """직교 벡터는 유사도 0.0."""
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_empty_or_zero_vector():
    """빈 벡터·영벡터는 0.0."""
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_similarity_length_mismatch_returns_zero():
    """길이가 다르면 zip 침묵 절단 대신 0.0 으로 안전 폴백한다."""
    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0


def test_max_cosine_similarity_empty_references():
    """참조셋이 비면 0.0."""
    assert max_cosine_similarity([1.0, 0.0], []) == 0.0
