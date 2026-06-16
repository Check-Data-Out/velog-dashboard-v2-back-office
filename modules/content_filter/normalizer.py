import re
import unicodedata
from dataclasses import dataclass

# zero-width / soft hyphen + 한글 필러 (한국 스팸이 띄어쓰기 위장에 악용)
INVISIBLE_CODEPOINTS = (
    0x200B,
    0x200C,
    0x200D,
    0x2060,
    0xFEFF,
    0x00AD,
    0x180E,
    0x115F,
    0x1160,
    0x3164,
    0xFFA0,
)
INVISIBLE_RE = re.compile(
    "[" + "".join(chr(c) for c in INVISIBLE_CODEPOINTS) + "]"
)

# 분리자: 공백 + 렉시콘 회피용 구분 기호 (despaced 뷰 생성에 사용)
SEPARATOR_RE = re.compile(r"[\s.\-_*^~/|·∙•・,]+")
WHITESPACE_RE = re.compile(r"\s+")

# 3회 이상 반복 문자를 2회로 축약 (도박!!!!! / ㅋㅋㅋㅋ / 대대대출)
REPEAT_RE = re.compile(r"(.)\1{2,}")

# 호환(compatibility) 자모가 2자 이상 연속하면 자모 분해 회피로 간주
ISOLATED_JAMO_RE = re.compile("[" + chr(0x3130) + "-" + chr(0x318F) + "]{2,}")

# 키릴/그리스 → 라틴 동형문자 폴딩 (ASCII 키워드 회피 방어, NFKC 이후 적용)
HOMOGLYPH_MAP = {
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "х": "x",
    "у": "y",
    "к": "k",
    "м": "m",
    "т": "t",
    "в": "b",
    "н": "h",
    "А": "A",
    "Е": "E",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Х": "X",
    "ο": "o",
    "α": "a",
    "ρ": "p",
    "ν": "v",
}
HOMOGLYPH_TABLE = {ord(k): v for k, v in HOMOGLYPH_MAP.items()}


@dataclass(frozen=True)
class NormalizedText:
    """정규화 결과. 어휘밀도 분석에는 spaced, 렉시콘 매칭에는 despaced 를 쓴다."""

    spaced: str
    despaced: str
    has_isolated_jamo: bool


def normalize(text: str) -> NormalizedText:
    """스팸 회피 기법을 무력화한 두 뷰(spaced/despaced)와 자모분해 플래그 반환.

    순서: invisible+한글필러 제거 → NFKC → 동형문자 폴딩 → 반복문자 축약
    → 공백 정리(spaced) → 분리자 제거(despaced).
    """
    if not text:
        return NormalizedText(spaced="", despaced="", has_isolated_jamo=False)

    stripped = INVISIBLE_RE.sub("", text)
    # NFKC 가 호환 자모를 음절로 재조합하므로 분해 회피 검출은 그 이전에 한다
    has_isolated_jamo = bool(ISOLATED_JAMO_RE.search(stripped))

    normalized = unicodedata.normalize("NFKC", stripped)
    folded = normalized.translate(HOMOGLYPH_TABLE)
    collapsed = REPEAT_RE.sub(r"\1\1", folded)

    spaced = WHITESPACE_RE.sub(" ", collapsed).strip()
    despaced = SEPARATOR_RE.sub("", spaced)

    return NormalizedText(
        spaced=spaced,
        despaced=despaced,
        has_isolated_jamo=has_isolated_jamo,
    )
