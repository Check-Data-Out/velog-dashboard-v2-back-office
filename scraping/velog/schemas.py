from dataclasses import dataclass


@dataclass
class User:
    id: str
    username: str
    email: str = ""


@dataclass
class Post:
    id: str  # UUID
    title: str
    short_description: str
    thumbnail: str | None = None
    url_slug: str | None = None
    released_at: str | None = None
    updated_at: str | None = None
    created_at: str | None = None
    body: str | None = None
    is_markdown: bool = False
    is_temp: bool = False
    is_private: bool = False
    likes: int = 0
    views: int = 0
    liked: bool = False
    comments_count: int = 0
    tags: list[str] | None = None
    user: User | None = None


@dataclass
class PostStats:
    id: str
    likes: int
    views: int
