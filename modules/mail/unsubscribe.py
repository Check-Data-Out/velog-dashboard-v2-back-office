"""뉴스레터 수신거부 링크 서명.

API 서버가 같은 형식으로 서명을 검증하므로 메시지 형식과 인코딩을 바꾸면
두 서버를 함께 바꿔야 한다.
"""

import base64
import hashlib
import hmac
from urllib.parse import quote

UNSUBSCRIBE_ENDPOINT = (
    "https://velog-dashboard.kro.kr/api/user/newsletter-unsubscribe"
)

# API 가 서명을 검증하는 키 최소 길이
MIN_SECRET_BYTES = 32


def is_usable_secret(secret: str) -> bool:
    """API 가 검증할 수 있는 서명 키(32바이트 이상)인지 확인한다."""
    return len(secret.encode()) >= MIN_SECRET_BYTES


def sign_unsubscribe(secret: str, uid: int) -> str:
    """사용자 id 의 수신거부 서명을 만든다.

    Args:
        secret: 수신거부 서명 키
        uid: 사용자 id

    Returns:
        HMAC-SHA256 값을 패딩 없는 base64url 로 인코딩한 문자열
    """
    digest = hmac.new(
        secret.encode(),
        f"newsletter-unsubscribe:{uid}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def build_unsubscribe_url(secret: str, uid: int) -> str:
    """사용자 id 의 서명된 수신거부 URL 을 만든다.

    Args:
        secret: 수신거부 서명 키
        uid: 사용자 id

    Returns:
        uid 와 서명을 쿼리로 담은 수신거부 URL
    """
    return (
        f"{UNSUBSCRIBE_ENDPOINT}?uid={uid}&sig={sign_unsubscribe(secret, uid)}"
    )


def build_legacy_unsubscribe_url(email: str) -> str:
    """서명 키가 없을 때 쓰는 기존 email 수신거부 URL 을 만든다.

    API 는 이 링크를 GET 으로 받으면 바로 수신거부한다.

    Args:
        email: 수신자 이메일

    Returns:
        email 을 쿼리로 담은 수신거부 URL
    """
    return f"{UNSUBSCRIBE_ENDPOINT}?email={quote(email, safe='@')}"
