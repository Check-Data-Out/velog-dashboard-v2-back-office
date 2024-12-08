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
