import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from asgiref.sync import async_to_sync
from django.conf import settings

from insight.models import UserWeeklyTrend
from posts.models import Post, PostDailyStatistics
from scraping.velog.schemas import Post as VelogPost
from users.models import User

KST = ZoneInfo("Asia/Seoul")
# 월요일 07:05 에 도는 배치. 분석 주차는 11/16(월) 00:00 ~ 11/23(월) 00:00
NOW = datetime(2026, 11, 23, 7, 5, tzinfo=KST)
WEEK_START = datetime(2026, 11, 16, tzinfo=KST)
WEEK_END = datetime(2026, 11, 23, tzinfo=KST)

NEW_POST_BODY = "이번 주에 쓴 글의 본문 전체"
LLM_RESULT = {
    "trending_summary": [
        {
            "title": "이번 주 새 글",
            "summary": "새 글 요약",
            "key_points": ["핵심 1", "핵심 2"],
        }
    ],
    "trend_analysis": {
        "hot_keywords": ["Django"],
        "title_trends": "제목 경향",
        "content_trends": "내용 경향",
        "insights": "인사이트",
    },
}


def create_user(username: str) -> User:
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        group_id=1,
        email=f"{username}@example.com",
        username=username,
        is_active=True,
        newsletter_subscribed=True,
    )


def create_post(
    user: User,
    title: str,
    released_at: datetime,
    stats: dict[datetime, tuple[int, int]],
) -> Post:
    """게시글과 날짜별 (조회수, 좋아요 수) 통계를 만든다"""
    post = Post.objects.create(
        post_uuid=uuid.uuid4(),
        user=user,
        title=title,
        slug=title,
        released_at=released_at,
    )
    for date, (views, likes) in stats.items():
        PostDailyStatistics.objects.create(
            post=post,
            date=date,
            daily_view_count=views,
            daily_like_count=likes,
        )
    return post


@pytest.fixture
def monday():
    """오늘을 월요일 07:05 KST 로 고정한다"""
    with patch("utils.utils.get_local_now", return_value=NOW):
        yield NOW


@pytest.fixture
def mock_velog_client_cls():
    """분석 컨텍스트가 만드는 VelogClient. 글마다 본문이 든 응답을 돌려준다"""

    async def get_post(post_uuid: str) -> VelogPost:
        return VelogPost(
            id=post_uuid,
            title="이번 주 새 글",
            short_description="",
            thumbnail="thumb.png",
            url_slug="new-post",
            body=NEW_POST_BODY,
        )

    with patch("insight.tasks.base_analysis.VelogClient") as client_cls:
        velog_client = AsyncMock()
        velog_client.get_post.side_effect = get_post
        client_cls.get_client.return_value = velog_client
        yield client_cls


@pytest.fixture
def mock_llm():
    with patch(
        "insight.tasks.weekly_user_trend_analysis.analyze_user_posts",
        return_value=LLM_RESULT,
    ) as llm:
        yield llm


@pytest.mark.django_db
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyUserTrendRun:
    def test_run_saves_trend_per_valid_user_and_reports_expired(
        self, analyzer_user, monday, mock_velog_client_cls, mock_llm
    ):
        """새 글 있는 사용자·없는 사용자는 저장하고, 토큰 만료 사용자는 빼고 보고한다"""
        writer = create_user("writer")
        create_post(
            writer,
            "예전 글",
            WEEK_START - timedelta(days=30),
            {WEEK_START: (100, 10), WEEK_END: (150, 12)},
        )
        new_post = create_post(
            writer,
            "이번 주 새 글",
            WEEK_START + timedelta(days=2, hours=10),
            {WEEK_END: (30, 3)},
        )
        quiet = create_user("quiet")
        create_post(
            quiet,
            "마지막 글",
            WEEK_END - timedelta(days=13) + timedelta(hours=9),
            {WEEK_START: (10, 1), WEEK_END: (25, 2)},
        )
        # 오늘자 통계가 없으면 토큰 만료로 본다
        expired = create_user("expired")
        create_post(
            expired,
            "통계가 끊긴 글",
            WEEK_START - timedelta(days=30),
            {WEEK_START: (5, 0)},
        )

        result = async_to_sync(analyzer_user.run)()

        assert result.success is True
        assert result.metadata == {
            "processed_count": 2,
            "expired_token_users": 1,
            "successful_users": 2,
            "expired_user_ids": [expired.id],
        }

        # LLM 은 새 글이 있는 사용자에게만 한 번, 본문 전체로 부른다
        mock_llm.assert_called_once_with(
            [{"제목": "이번 주 새 글", "내용": NEW_POST_BODY}],
            settings.OPENAI_API_KEY,
        )
        velog_client = mock_velog_client_cls.get_client.return_value
        velog_client.get_post.assert_awaited_once_with(str(new_post.post_uuid))

        rows = {
            row.user_id: row
            for row in UserWeeklyTrend.objects.filter(
                week_start_date=WEEK_START.date(),
                week_end_date=(WEEK_END - timedelta(days=1)).date(),
                is_processed=False,
            )
        }
        assert set(rows) == {writer.id, quiet.id}
        assert UserWeeklyTrend.objects.count() == 2
        assert rows[writer.id].insight == {
            "trending_summary": [
                {
                    "title": "이번 주 새 글",
                    "summary": "새 글 요약",
                    "key_points": ["핵심 1", "핵심 2"],
                    "username": "writer",
                    "thumbnail": "thumb.png",
                    "slug": "new-post",
                }
            ],
            "trend_analysis": LLM_RESULT["trend_analysis"],
            "user_weekly_stats": {
                "posts": 2,
                "new_posts": 1,
                "views": 80,
                "likes": 5,
            },
            "user_weekly_reminder": None,
        }
        assert rows[quiet.id].insight == {
            "trending_summary": [],
            "trend_analysis": None,
            "user_weekly_stats": {
                "posts": 1,
                "new_posts": 0,
                "views": 15,
                "likes": 1,
            },
            "user_weekly_reminder": {"title": "마지막 글", "days_ago": 13},
        }

    def test_fetch_data_returns_only_newsletter_target_users(
        self, analyzer_user
    ):
        """이메일이 있고 활성이며 수신 동의한 사용자의 id·username 만 돌려준다"""
        target = create_user("target")
        User.objects.filter(pk=create_user("inactive").pk).update(
            is_active=False
        )
        User.objects.filter(pk=create_user("unsubscribed").pk).update(
            newsletter_subscribed=False
        )
        User.objects.filter(pk=create_user("no-email").pk).update(email="")

        users = async_to_sync(analyzer_user._fetch_data)(None)

        assert users == [{"id": target.id, "username": "target"}]
