import re

from insight.filtering.constants import (
    CATEGORY_LEXICONS,
    DEV_DOMAIN_ALLOWLIST,
    DEV_TOKENS,
    OFFTOPIC_CATEGORIES,
)

PHONE_RE = re.compile(r"01[016789]\d{7,8}")
KAKAO_TOKENS = ("카톡", "카카오톡", "오픈채팅", "오픈톡", "openkakao")
TELEGRAM_TOKENS = ("텔레그램", "telegram", "tme")
CODE_FENCE_RE = re.compile(r"```|~~~")
INLINE_CODE_RE = re.compile(r"`[^`]+`")
URL_RE = re.compile(r"https?://[^\s)]+")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
TOKEN_RE = re.compile(r"[a-zA-Z]+|[가-힣]+")


def detect_contacts(despaced: str) -> list[str]:
    """연락처/메신저 채널 검출. despaced 뷰(분리자 제거)에 매칭한다."""
    channels = []
    if PHONE_RE.search(despaced):
        channels.append("phone")
    low = despaced.lower()
    if any(t in despaced or t in low for t in KAKAO_TOKENS):
        channels.append("kakao")
    if any(t in despaced or t in low for t in TELEGRAM_TOKENS):
        channels.append("telegram")
    return channels


def match_lexicons(despaced: str) -> dict[str, list[str]]:
    """카테고리별 광고 렉시콘 매칭 결과 (despaced 뷰)."""
    hits = {}
    for category, lexicon in CATEGORY_LEXICONS.items():
        matched = [term for term in lexicon if term in despaced]
        if matched:
            hits[category] = matched
    return hits


def dev_token_hits(spaced: str) -> int:
    """본문에 등장한 개발 어휘(중복 제거) 수. 온토픽 판정의 핵심 신호."""
    low = spaced.lower()
    return sum(1 for token in DEV_TOKENS if token in low)


def has_code_block(body: str) -> bool:
    """코드 펜스 또는 인라인 코드 존재 여부."""
    return bool(CODE_FENCE_RE.search(body) or INLINE_CODE_RE.search(body))


def tag_signal(tags: list[str]) -> dict[str, object]:
    """태그의 개발 비율과 오프토픽 태그 목록."""
    if not tags:
        return {"dev_tag_ratio": 0.0, "offtopic": [], "count": 0}

    dev = sum(1 for t in tags if t.lower() in DEV_TOKENS)
    offtopic = [
        t
        for t in tags
        for category in OFFTOPIC_CATEGORIES
        if t in CATEGORY_LEXICONS[category]
    ]
    return {
        "dev_tag_ratio": dev / len(tags),
        "offtopic": offtopic,
        "count": len(tags),
    }


def link_signal(body: str) -> dict[str, int]:
    """외부 링크 수와 개발 도메인/비개발 도메인 분류."""
    urls = URL_RE.findall(body)
    dev_links = sum(
        1 for u in urls if any(domain in u for domain in DEV_DOMAIN_ALLOWLIST)
    )
    return {
        "link_count": len(urls),
        "dev_link_count": dev_links,
        "nondev_link_count": len(urls) - dev_links,
    }


def image_text_ratio(body: str) -> float:
    """이미지 수 대비 텍스트 길이 비율 (이미지 덤프 검출). 높을수록 의심."""
    images = len(IMAGE_RE.findall(body))
    if images == 0:
        return 0.0
    text_len = len(IMAGE_RE.sub("", body).strip())
    return images / max(1.0, text_len / 100)
