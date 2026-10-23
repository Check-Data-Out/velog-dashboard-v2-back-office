"""뉴스레터 수신거부 링크 서명.

API 서버가 같은 형식으로 서명을 검증하므로 메시지 형식과 인코딩을 바꾸면
두 서버를 함께 바꿔야 한다.
"""

import base64
import hashlib
import hmac


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
