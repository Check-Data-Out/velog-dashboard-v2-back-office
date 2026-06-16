import pytest

from insight.filtering import signals


def test_detect_phone_number():
    """공백/하이픈 제거된 despaced 에서 휴대폰 번호를 검출한다."""
    assert "phone" in signals.detect_contacts("01012345678")


def test_detect_messenger_handles():
    """카카오/텔레그램 메신저 유도를 검출한다."""
    assert "kakao" in signals.detect_contacts("오픈채팅링크주소")
    assert "telegram" in signals.detect_contacts("텔레그램으로문의")


@pytest.mark.parametrize(
    "category, despaced",
    [
        ("adult", "노래방도우미급구"),
        ("gambling", "토토사이트추천"),
        ("drug", "비아그라판매"),
    ],
)
def test_lexicon_category_match(category, despaced):
    """카테고리별 광고 렉시콘이 despaced 에서 매칭된다."""
    assert category in signals.match_lexicons(despaced)


def test_loan_and_recruit_are_distinct_categories():
    """대출/모집은 별도 약신호 카테고리로 잡힌다."""
    hits = signals.match_lexicons("고수익대출가능")
    assert "recruit" in hits
    assert "loan" in hits


def test_dev_token_hits_high_for_dev_zero_for_offtopic():
    """개발 글은 어휘 hit 가 높고 오프토픽은 0 이다."""
    assert signals.dev_token_hits("서버 배포 api 도커 깃") >= 3
    assert signals.dev_token_hits("노래방 모집 급구 문의") == 0


def test_has_code_block():
    """코드 펜스/인라인 코드를 검출한다."""
    assert signals.has_code_block("```python\nx = 1\n```") is True
    assert signals.has_code_block("그냥 평범한 문장입니다") is False


def test_tag_signal_dev_vs_offtopic():
    """태그의 개발 비율과 오프토픽 태그를 산출한다."""
    dev = signals.tag_signal(["python", "react"])
    assert dev["dev_tag_ratio"] == 1.0

    off = signals.tag_signal(["토토", "react"])
    assert off["offtopic"] == ["토토"]


def test_link_signal_classifies_domains():
    """외부 링크를 개발/비개발 도메인으로 분류한다."""
    body = "참고 https://github.com/a 그리고 https://evilcasino.example/b"
    sig = signals.link_signal(body)
    assert sig["link_count"] == 2
    assert sig["dev_link_count"] == 1
    assert sig["nondev_link_count"] == 1


def test_image_text_ratio_high_for_image_dump():
    """이미지 덤프(이미지 다수 + 본문 빈약)는 일반 글보다 비율이 높다."""
    dump = "![](a.png)![](b.png)![](c.png) 짧음"
    normal = "![](a.png) " + "긴 본문 내용이 이어집니다 " * 30
    assert signals.image_text_ratio(dump) > signals.image_text_ratio(normal)
