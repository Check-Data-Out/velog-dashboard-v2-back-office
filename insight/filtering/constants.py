"""광고/스팸 분류용 렉시콘·시드 토큰·임계.

임계값은 과거 누출 샘플 확보 후 보정 전 placeholder 다. 도박은 한국 스팸의
다수를 차지하므로 최우선 가중한다.
"""

# 오프토픽 광고 렉시콘 (개발 무관). despaced 뷰(분리자 제거)에 매칭하므로
# 일반어 오탐(도우미=helper, 출장=출장보고)을 피해 광고 collocation 으로 좁힌다.
ADULT_LEXICON = frozenset(
    {
        "노래방도우미",
        "애인대행",
        "조건만남",
        "출장마사지",
        "출장안마",
        "유흥알바",
        "성인용품",
    }
)
GAMBLING_LEXICON = frozenset(
    {
        "온라인카지노",
        "카지노사이트",
        "사설토토",
        "스포츠토토",
        "바카라사이트",
        "먹튀검증",
        "꽁머니",
        "슬롯사이트",
    }
)
DRUG_LEXICON = frozenset(
    {
        "비아그라",
        "시알리스",
        "흥분제",
    }
)
LOAN_LEXICON = frozenset(
    {
        "무담보대출",
        "작업대출",
        "햇살론",
        "신용대출",
        "일수대출",
    }
)
RECRUIT_LEXICON = frozenset(
    {
        "고수익알바",
        "고수익부업",
        "당일지급",
        "초보가능",
        "미경험가능",
        "고액알바",
    }
)

# 단독으로는 강신호가 아닌(개발 커리어·핀테크 글 보호) 약신호 카테고리
WEAK_CATEGORIES = frozenset({"loan", "recruit"})
# 단독 1건으로도 drop 하는 high-harm 카테고리
HIGH_HARM_CATEGORIES = frozenset({"adult", "gambling", "drug"})
# 개발 무관 광고 카테고리 전체
OFFTOPIC_CATEGORIES = HIGH_HARM_CATEGORIES | WEAK_CATEGORIES

CATEGORY_LEXICONS = {
    "adult": ADULT_LEXICON,
    "gambling": GAMBLING_LEXICON,
    "drug": DRUG_LEXICON,
    "loan": LOAN_LEXICON,
    "recruit": RECRUIT_LEXICON,
}

# 개발 어휘 시드 (온토픽 판정). 운영 시 과거 본문 코퍼스에서 보강.
DEV_TOKENS = frozenset(
    {
        "javascript",
        "typescript",
        "python",
        "java",
        "react",
        "vue",
        "svelte",
        "django",
        "spring",
        "fastapi",
        "nextjs",
        "node",
        "api",
        "서버",
        "배포",
        "함수",
        "변수",
        "클래스",
        "알고리즘",
        "자료구조",
        "데이터베이스",
        "쿼리",
        "도커",
        "쿠버네티스",
        "깃",
        "github",
        "컴파일",
        "디버깅",
        "리팩토링",
        "비동기",
        "테스트",
        "라이브러리",
        "프레임워크",
        "캐시",
        "스레드",
        "컴포넌트",
        "구현",
        "개발",
        "코드",
        "프로그래밍",
        "빌드",
        "메서드",
        "모듈",
        "패키지",
        "인터페이스",
        "리액트",
        "타입스크립트",
        "파이썬",
    }
)

# 본문 링크가 개발 도메인이면 감점
DEV_DOMAIN_ALLOWLIST = frozenset(
    {
        "github.com",
        "stackoverflow.com",
        "developer.mozilla.org",
        "velog.io",
        "medium.com",
        "dev.to",
    }
)

# 임계 (placeholder, 라벨 확보 후 보정)
DEV_DENSITY_LOW_THRESHOLD = 0.02
SPAM_SCORE_DROP_THRESHOLD = 0.6
SPAM_SCORE_PASS_THRESHOLD = 0.25
