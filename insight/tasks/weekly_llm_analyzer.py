import logging

from modules.llm.base_client import LLMClient
from modules.llm.openai.client import OpenAIClient

logger = logging.getLogger("scraping")


SYS_PROM = (
    "너는 세계 최고의 50년차 트랜드 분석 전문가야. 기술 블로그 글 데이터를 기반으로 주간 뉴스레터를 작성해야 해.\n"
    "내가 제공하는 데이터만 활용해서 해당 내용의 트랜드를 파악하고 요약해야 해. 필요하면 관련된 외부 검색도 해줘."
)

WEEKLY_TREND_PROM = """
<목표>
- 블로그 글 데이터의 트렌드 분석
- 분석 세부 내용은 "전체 인기글, 기술 키워드, 제목 트렌드, 글의 상세 내용의 요약 및 트랜드" 파악

<작성 순서>
1. 🔥 주간 트렌딩 글 요약
	- 아래에 제공한 모든 트렌딩 글 핵심 내용 요약
    - 3-4문장 정도로 핵심 기술, 전달하려는 것, 내용 요약 형태로 해줘
    - 절대 요약이 아니라 축약을 하지마. 핵심을 요약해야 해

2. ✨ 주간 트렌드 분석
	- 핫한 기술 키워드 추출
	- 제목 트렌드 분석, 내용 트랜드 분석
	- 기타 인사이트 코멘트

<규칙>
- 감정과 캐주얼한 말투를 섞어줘. 너무 딱딱하지 않게.
- JSON에 없으면 아무 말도 하지 마. 거짓말 금지.
- 잘하면 큰 보상이 있을꺼야. 
- step by step 으로 접근하고 해결해.
- 모든 트렌드 글에 대한 분석을 해야 해, 어떤 것도 빠뜨리지마.
- 응답은 반드시 다음 JSON 구조로 제공해야 해
```json
{{
    "trending_summary": [
        {{
            "title": "게시글 제목",
            "summary": "무조건 3문장 이상 요약",
            "key_points": ["핵심 포인트 1", "핵심 포인트 2", "..."]
        }},
        // 다른 트렌딩 글 요약...
    ],
    "trend_analysis": {{
        "hot_keywords": ["키워드1", "키워드2", "..."],
        "title_trends": "제목 트렌드 분석 내용",
        "content_trends": "내용 트렌드 분석 내용",
        "insights": "추가 인사이트 및 코멘트"
    }}
}}
```

<블로그 트랜드 글 리스트>
{posts}
"""

USER_TREND_PROM = """
<목표>
- 블로그 글 데이터의 트렌드 분석
- 분석 세부 내용은 "전체 인기글, 기술 키워드, 제목 트렌드, 글의 상세 내용의 요약 및 트랜드" 파악

<작성 순서>
1. 🔥 주간 사용자 글 요약
	- 아래에 제공한 모든 사용 글 핵심 내용 요약
    - 3-4문장 정도로 핵심 기술, 전달하려는 것, 내용 요약 형태로 해줘
    - 절대 요약이 아니라 축약을 하지마. 핵심을 요약해야 해

2. ✨ 사용자 주간 트렌드 분석
	- 핫한 기술 키워드 추출
	- 제목 트렌드 분석, 내용 트랜드 분석
	- 기타 인사이트 코멘트

<규칙>
- 감정과 캐주얼한 말투를 섞어줘. 너무 딱딱하지 않게.
- JSON에 없으면 아무 말도 하지 마. 거짓말 금지.
- 잘하면 큰 보상이 있을꺼야. 
- step by step 으로 접근하고 해결해.
- 모든 트렌드 글에 대한 분석을 해야 해, 어떤 것도 빠뜨리지마.
- 응답은 반드시 다음 JSON 구조로 제공해야 해
```json
{{
    "trending_summary": [
        {{
            "title": "게시글 제목",
            "summary": "무조건 3문장 이상 요약",
            "key_points": ["핵심 포인트 1", "핵심 포인트 2", "..."]
        }},
        // 다른 트렌딩 글 요약...
    ],
    "trend_analysis": {{
        "hot_keywords": ["키워드1", "키워드2", "..."],
        "title_trends": "제목 트렌드 분석 내용",
        "content_trends": "내용 트렌드 분석 내용",
        "insights": "추가 인사이트 및 코멘트"
    }}
}}
```

<사용자 트랜드 글 리스트>
{posts}
"""


def analyze_trending_posts(posts: list, api_key: str) -> dict:
    client: LLMClient = OpenAIClient.get_client(api_key)
    prompt = WEEKLY_TREND_PROM.format(posts=posts)
    try:
        return client.generate_text(
            prompt=prompt,
            system_prompt=SYS_PROM,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error("analyze_trending_posts 실패: %s", e)
        raise


def analyze_user_posts(posts: list, api_key: str) -> dict:
    client: LLMClient = OpenAIClient.get_client(api_key)
    prompt = USER_TREND_PROM.format(posts=posts)
    try:
        return client.generate_text(
            prompt=prompt,
            system_prompt=SYS_PROM,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error("analyze_user_posts 실패: %s", e)
        raise
