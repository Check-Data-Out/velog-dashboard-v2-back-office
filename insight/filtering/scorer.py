from insight.filtering.constants import (
    HIGH_HARM_CATEGORIES,
    IMAGE_DUMP_RATIO,
    SPAM_SCORE_DROP_THRESHOLD,
    SPAM_SCORE_PASS_THRESHOLD,
    WEAK_CATEGORIES,
)
from insight.filtering.schemas import (
    VERDICT_BORDERLINE,
    VERDICT_DROP,
    VERDICT_PASS,
    FilterVerdict,
)
from insight.filtering.signals import (
    detect_contacts,
    dev_token_hits,
    has_code_block,
    image_text_ratio,
    link_signal,
    match_lexicons,
    tag_signal,
)
from modules.content_filter.normalizer import normalize


def verdict_from_score(score: float) -> str:
    """누적 spam_score 를 임계로 drop/pass/borderline 판정한다(단일 진실 원천)."""
    if score >= SPAM_SCORE_DROP_THRESHOLD:
        return VERDICT_DROP
    if score <= SPAM_SCORE_PASS_THRESHOLD:
        return VERDICT_PASS
    return VERDICT_BORDERLINE


def score_post(body: str, title: str, tags: list[str]) -> FilterVerdict:
    """휴리스틱 신호를 융합해 글 1개의 필터 판정을 반환한다.

    정책: 개발 무관 오프토픽(유흥/도박/약물)만 공격적으로 drop, 개발 관련 글은
    연락처/모집 렉시콘이 있어도 통과시킨다(FN≫FP 비대칭).
    """
    norm = normalize(f"{title}\n{body}")
    contacts = detect_contacts(norm.despaced)
    lexicons = match_lexicons(norm.despaced)
    dev_hits = dev_token_hits(norm.spaced)
    code = has_code_block(body)
    tagsig = tag_signal(tags)

    triggered: list[str] = []
    if contacts:
        triggered.append(f"contact:{','.join(contacts)}")
    for category, terms in lexicons.items():
        triggered.append(f"{category}:{','.join(terms)}")

    # 온토픽 판정은 본문 신호(dev 어휘/코드)만으로 — 태그는 공격자 통제라 제외
    is_offtopic = dev_hits == 0 and not code
    if is_offtopic:
        triggered.append("offtopic")

    # hard rule 1: high-harm 카테고리는 단독으로도 drop (구별력 있는 collocation
    # 렉시콘이라 일반어 오탐 위험이 낮음)
    high_harm = [c for c in lexicons if c in HIGH_HARM_CATEGORIES]
    if high_harm:
        return FilterVerdict(
            verdict=VERDICT_DROP,
            score=1.0,
            category=high_harm[0],
            triggered_signals=triggered,
        )

    # hard rule 2: 오프토픽 + (연락처 | 오프토픽 태그). 약신호 렉시콘 단독은
    # 정상 개인글(예: "대출 다 갚았습니다")을 drop 하지 않도록 soft score 로만.
    weak_hit = [c for c in lexicons if c in WEAK_CATEGORIES]
    if is_offtopic and (contacts or tagsig["offtopic"]):
        return FilterVerdict(
            verdict=VERDICT_DROP,
            score=0.9,
            category="offtopic",
            triggered_signals=triggered,
        )

    # soft score (recall 편향, dev 신호는 감점)
    links = link_signal(body)
    score = 0.0
    score += 0.2 * len(weak_hit)
    score += 0.25 if contacts else 0.0
    score += 0.35 if is_offtopic else 0.0
    score += 0.2 if tagsig["offtopic"] else 0.0
    score += 0.15 if image_text_ratio(body) >= IMAGE_DUMP_RATIO else 0.0
    score += min(0.15, 0.05 * links["nondev_link_count"])
    score -= min(0.4, 0.15 * dev_hits)
    score = max(0.0, min(1.0, score))

    return FilterVerdict(
        verdict=verdict_from_score(score),
        score=round(score, 3),
        category="",
        triggered_signals=triggered,
    )
