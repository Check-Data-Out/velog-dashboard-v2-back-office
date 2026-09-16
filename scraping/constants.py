from typing import Final

V3_URL: Final[str] = "https://v3.velog.io/graphql"

VELOG_POSTS_QUERY: Final[str] = """
    query velogPosts($input: GetPostsInput!) {
        posts(input: $input) {
            id
            title
            url_slug
            likes
            views
            released_at
        }
    }
    """

CURRENT_USER_QUERY: Final[str] = """
    query currentUser {
        currentUser {
            id
            username
            email
            profile {
                thumbnail
            }
        }
    }
    """
