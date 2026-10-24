from modules.mail.unsubscribe import (
    build_legacy_unsubscribe_url,
    sign_unsubscribe,
)

TEST_SECRET = "test-newsletter-unsubscribe-secret-0123456789"


def test_sign_unsubscribe_matches_shared_vector_without_padding() -> None:
    """API 와 공유하는 고정 벡터와 같은 패딩 없는 base64url 서명을 만든다."""
    signature = sign_unsubscribe(TEST_SECRET, 42)

    assert signature == "PJT8snaX4RoJtPxS8SJBVracgxS_c0eIMiT9gFKdIKc"
    assert "=" not in signature


def test_build_legacy_unsubscribe_url_encodes_plus_in_email() -> None:
    """이메일의 + 를 인코딩해 API 가 공백으로 읽지 않게 한다."""
    url = build_legacy_unsubscribe_url("a+b@example.com")

    assert url.endswith("?email=a%2Bb@example.com")
