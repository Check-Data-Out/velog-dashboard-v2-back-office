from modules.mail.unsubscribe import sign_unsubscribe

TEST_SECRET = "test-newsletter-unsubscribe-secret-0123456789"


def test_sign_unsubscribe_matches_shared_vector_without_padding() -> None:
    """API 와 공유하는 고정 벡터와 같은 패딩 없는 base64url 서명을 만든다."""
    signature = sign_unsubscribe(TEST_SECRET, 42)

    assert signature == "PJT8snaX4RoJtPxS8SJBVracgxS_c0eIMiT9gFKdIKc"
    assert "=" not in signature


def test_sign_unsubscribe_differs_by_uid() -> None:
    """다른 uid 는 다른 서명을 만든다."""
    assert sign_unsubscribe(TEST_SECRET, 42) != sign_unsubscribe(
        TEST_SECRET, 43
    )
