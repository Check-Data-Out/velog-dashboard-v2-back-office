from typing import Final

CURRENT_USER_QUERY: Final[str] = """
    query currentUser {
        currentUser {
            id
            username
            email
        }
    }
    """

VELOG_POSTS_QUERY: Final[str] = """
    query velogPosts($input: GetPostsInput!) {
        posts(input: $input) {
            id
            title
        }
    }
    """
