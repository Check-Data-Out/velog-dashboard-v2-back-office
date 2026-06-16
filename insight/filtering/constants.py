"""광고/스팸 분류용 렉시콘·시드 토큰·임계.

임계값은 과거 누출 샘플 확보 후 보정 전 placeholder 다. 도박은 한국 스팸의
다수를 차지하므로 최우선 가중한다.
"""

# 오프토픽 광고 렉시콘 (개발 무관). despaced 뷰에 매칭한다.
ADULT_LEXICON = frozenset(
    {
        "노래방",
        "도우미",
        "가라오케",
        "텐프로",
        "출장",
        "마사지",
        "안마",
        "애인대행",
        "모텔",
        "룸",
    }
)
GAMBLING_LEXICON = frozenset(
    {
        "토토",
        "배팅",
        "베팅",
        "카지노",
        "슬롯",
        "바카라",
        "먹튀",
        "꽁머니",
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
        "대출",
        "작업대출",
        "햇살론",
        "무담보",
        "신용불량",
    }
)
RECRUIT_LEXICON = frozenset(
    {
        "고수익",
        "고소득",
        "일당",
        "일급",
        "주급",
        "당일지급",
        "초보가능",
        "미경험",
    }
)

# 단독으로는 강신호가 아닌(개발 커리어·핀테크 글 보호) 약신호 카테고리
WEAK_CATEGORIES = frozenset({"loan", "recruit"})
# 단독 1건으로도 drop 하는 high-harm 카테고리
HIGH_HARM_CATEGORIES = frozenset({"adult", "gambling", "drug"})

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
        "쿼리",
        "캐시",
        "스레드",
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
