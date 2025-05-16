from typing import Final

# API 엔드포인트
V3_URL: Final[str] = "https://v3.velog.io/graphql"
"""Velog API v3 엔드포인트 URL"""

V2_URL: Final[str] = "https://v2.velog.io/graphql"
"""Velog API v2 엔드포인트 URL"""

V2_CDN_URL: Final[str] = "https://v2cdn.velog.io/graphql"
"""Velog API v2 CDN 엔드포인트 URL (통계 정보 등에 사용)"""


CURRENT_USER_QUERY: Final[str] = """
query currentUser {
    currentUser {
        id
        username
        email
    }
}
""".strip()
"""
현재 인증된 사용자의 정보를 조회하는 쿼리

반환 필드:
- id: 사용자 ID
- username: 사용자 이름
- email: 이메일 (빈 값일 수 있음, 특히 OAuth)
"""


POSTS_QUERY: Final[str] = """
query velogPosts($input: GetPostsInput!) {
    posts(input: $input) {
        id
        title
        short_description
        thumbnail
        url_slug
        released_at
        updated_at
        user {
            id
            username
        }
    }
}
""".strip()
"""
특정 사용자의 게시물 목록을 조회하는 쿼리

파라미터:
- input: PostsInput! 타입의 입력 객체
  - username: 사용자 아이디
  - tag: 태그로 필터링 (선택)
  - cursor: 페이지네이션을 위한 커서 (선택)
  - limit: 한번에 가져올 게시물 수 (선택, 기본값 10)

반환 필드:
- id: 게시물 ID
- title: 제목
- short_description: 요약 설명
- thumbnail: 썸네일 이미지 URL
- url_slug: URL 슬러그
- released_at: 발행일
- updated_at: 최종 수정일
- user: 작성자 정보 (id, username)
"""


POSTS_STATS_QUERY: Final[str] = """
query GetStats($post_id: ID!) {
    getStats(post_id: $post_id) {
        id
        likes
        views
    }
}
""".strip()
"""
게시물의 통계 정보를 조회하는 쿼리

파라미터:
- post_id: 게시물 ID

반환 필드:
- id: 게시물 ID
- likes: 좋아요 수
- views: 조회수
"""


GET_POST_QUERY: Final[str] = """
query GetPost($id: ID) {
    post(id: $id) {
        id
        title
        body
        short_description
        thumbnail
        is_markdown
        is_temp
        url_slug
        likes
        views
        is_private
        released_at
        created_at
        updated_at
        user {
            id
            username
        }
        tags
        comments_count
        liked
    }
}
""".strip()
"""
특정 게시물의 상세 정보를 조회하는 쿼리

파라미터:
- id: 게시물 ID

반환 필드:
- id: 게시물 ID
- title: 제목
- body: 본문 내용
- short_description: 요약 설명
- thumbnail: 썸네일 이미지 URL
- is_markdown: 마크다운 형식 여부
- is_temp: 임시 글 여부
- url_slug: URL 슬러그
- likes: 좋아요 수
- views: 조회수
- is_private: 비공개 여부
- released_at: 발행일
- created_at: 생성일
- updated_at: 최종 수정일
- user: 작성자 정보 (id, username)
- tags: 태그 목록
- comments_count: 댓글 수
- liked: 현재 사용자의 좋아요 여부
"""


TRENDING_POSTS_QUERY: Final[str] = """
query trendingPosts($input: TrendingPostsInput!) {
    trendingPosts(input: $input) {
        id
        title
        short_description
        thumbnail
        likes
        user {
            id
            username
            profile {
                id
                thumbnail
                display_name
            }
        }
        url_slug
        released_at
        updated_at
        is_private
        comments_count
    }
}
""".strip()
"""
인기 게시물 목록을 조회하는 쿼리

파라미터:
- input: TrendingPostsInput! 타입의 입력 객체
  - limit: 가져올 게시물 수 (기본값: 20)
  - offset: 오프셋 (기본값: 0)
  - timeframe: 기간 ('day', 'week', 'month', 'year' 중 하나)

반환 필드:
- id: 게시물 ID
- title: 제목
- short_description: 요약 설명
- thumbnail: 썸네일 이미지 URL
- likes: 좋아요 수
- user: 작성자 정보
  - id: 사용자 ID
  - username: 사용자 아이디
  - profile: 프로필 정보
    - id: 프로필 ID
    - thumbnail: 프로필 이미지 URL
    - display_name: 표시 이름
- url_slug: URL 슬러그
- released_at: 발행일
- updated_at: 최종 수정일
- is_private: 비공개 여부
- comments_count: 댓글 수
"""
