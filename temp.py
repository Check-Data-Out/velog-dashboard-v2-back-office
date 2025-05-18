"""
- 해당 파일은 django 에 의존성 없어요. django 없이 stand alone 으로 실행가능하게 테스트용으로 만들어 둠
- 고로 OPENAI_API_KEY 값은 환경 변수 없이 그냥 직접 넣어서 테스트 해주세요!!
"""

import asyncio

import aiohttp

from modules.llm.openai.client import OpenAIClient
from scraping.velog.exceptions import VelogError
from scraping.velog.services import VelogService

OPENAI_API_KEY = "sk-proj"  # "여기에 제가 공유한 토큰 써주세요!"

SYS_PROM = (
    "너는 세계 최고의 50년차 트랜드 분석 전문가야. 기술 블로그 글 데이터를 기반으로 주간 뉴스레터를 작성해야 해.\n"
    "내가 제공하는 데이터만 활용해서 해당 내용의 트랜드를 파악하고 요약해야 해. 필요하면 관련된 외부 검색도 해줘."
)

USER_PROM = """
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


def call_llm(posts):
    openai_client = OpenAIClient.get_client(OPENAI_API_KEY)
    creative_response = openai_client.generate_text(
        prompt=USER_PROM.format(posts=posts),
        system_prompt=SYS_PROM,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return creative_response


# 비동기 함수 실행
async def main():
    access_token = ""
    refresh_token = ""
    user_posts = list()
    trand_posts = list()

    # HTTP 세션 생성
    async with aiohttp.ClientSession() as session:
        # Velog 서비스 생성
        velog_service = VelogService(session, access_token, refresh_token)

        try:
            print(
                "==================================================================="
            )
            print("특정 사용자 게시물 가져와서 LLM 활용해서 트랜드 분석하기")
            print(
                "==================================================================="
            )

            user = await velog_service.get_current_user()
            if not user:
                print("사용자 인증 실패")
                return

            print(f"로그인 사용자: {user.username}")

            # 사용자의 게시물 가져오기
            try:
                all_user_posts = await velog_service.get_all_posts(
                    user.username
                )
                print(f"게시물 수: {len(all_user_posts)}")
                if not all_user_posts:
                    print("게시글 미존재")
                    return

                # 특정 게시물 상세 정보 가져오기, 테스트 전용, 20개로 제한
                # 여기서 "최근 일주일 간 작성된 게시글을 가져오는 로직" 이 추가됨이 필요 할 듯
                for post in all_user_posts[:20]:
                    post_detail = await velog_service.get_post(post.id)

                    if not post_detail:
                        continue

                    user_posts.append(
                        {
                            "제목": post_detail.title,
                            "내용": post_detail.body,
                            "댓글 수": post_detail.comments_count,
                            "좋아요 수": post_detail.likes,
                        }
                    )
            except VelogError as e:
                print(f"게시물 가져오기 실패: {e}")

            user_result = call_llm(user_posts)
            print(user_result)

            print(
                "==================================================================="
            )
            print("인기 게시물 가져와서 LLM 활용해서 트랜드 분석하기")
            print(
                "==================================================================="
            )

            # 인기 게시물 가져오기
            try:
                trending_posts = await velog_service.get_trending_posts(
                    limit=10
                )
                print(f"인기 게시물 수: {len(trending_posts)}")
                for post in trending_posts:
                    print(f"- {post.title} (좋아요: {post.likes})")
                    post_detail = await velog_service.get_post(post.id)
                    trand_posts.append(
                        {
                            "제목": post_detail.title,
                            "내용": post_detail.body,
                            "댓글 수": post_detail.comments_count,
                            "좋아요 수": post_detail.likes,
                        }
                    )
            except VelogError as e:
                print(f"인기 게시물 가져오기 실패: {e}")

            trand_result = call_llm(trand_posts)
            print(trand_result)
        except VelogError as e:
            print(f"Velog API 오류: {e}")
        except Exception as e:
            print(f"예상치 못한 오류: {e}")


if __name__ == "__main__":
    # 이벤트 루프 실행
    # 07df3e14-b899-49ce-a252-4a6c30d03233
    asyncio.run(main())
