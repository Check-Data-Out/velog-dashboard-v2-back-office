import pytest

from modules.content_filter.normalizer import normalize

ZERO_WIDTH = chr(0x200B)
HANGUL_FILLER = chr(0x3164)


@pytest.mark.parametrize(
    "raw, expected_despaced",
    [
        ("노 래 방", "노래방"),  # 공백 삽입
        ("노.래.방", "노래방"),  # 구분 기호 삽입
        ("노^^래방", "노래방"),  # 특수문자 삽입
        (f"노{ZERO_WIDTH}래{ZERO_WIDTH}방", "노래방"),  # zero-width
        (f"노{HANGUL_FILLER}래방", "노래방"),  # 한글 필러
        ("ＮＦＫＣ", "NFKC"),  # 전각 → 반각 (NFKC)
        ("도박!!!!!", "도박!!"),  # 반복 문자 축약
    ],
)
def test_normalize_neutralizes_evasion(raw, expected_despaced):
    """대표적인 회피 기법이 동일 despaced 형태로 수렴한다."""
    assert normalize(raw).despaced == expected_despaced


def test_isolated_jamo_flag():
    """분리 자모열이 자모 분해 회피로 플래그된다."""
    assert normalize("ㄴㅗㄹㅐㅂㅏㅇ").has_isolated_jamo is True
    assert normalize("노래방").has_isolated_jamo is False


def test_normalize_returns_spaced_and_despaced():
    """spaced(어휘밀도용)와 despaced(렉시콘용) 두 뷰를 모두 반환한다."""
    result = normalize("리액트 서버 컴포넌트")
    assert result.spaced == "리액트 서버 컴포넌트"
    assert result.despaced == "리액트서버컴포넌트"


def test_normalize_idempotent():
    """정규화는 멱등하다 (재적용해도 결과 불변)."""
    raw = "노 래   방!!!!"
    once = normalize(raw)
    twice = normalize(once.spaced)
    assert once.spaced == twice.spaced
    assert once.despaced == twice.despaced


@pytest.mark.parametrize("empty", ["", None])
def test_normalize_empty_input(empty):
    """빈/None 입력은 빈 결과로 안전하게 처리된다."""
    result = normalize(empty)
    assert result.spaced == ""
    assert result.despaced == ""
    assert result.has_isolated_jamo is False


def test_normalize_preserves_normal_korean():
    """정상 개발 문장은 훼손되지 않는다 (false positive 방지)."""
    text = "리액트 18의 서버 컴포넌트와 비동기 렌더링을 배포 환경에서 테스트했습니다."
    result = normalize(text)
    assert result.spaced == text
    assert "서버컴포넌트" in result.despaced


def test_normalize_folds_homoglyphs():
    """키릴 동형문자가 라틴으로 폴딩되어 회피를 무력화한다."""
    cyrillic_api = "а" + "pi"  # 첫 글자가 키릴 U+0430
    assert normalize(cyrillic_api).despaced == "api"
