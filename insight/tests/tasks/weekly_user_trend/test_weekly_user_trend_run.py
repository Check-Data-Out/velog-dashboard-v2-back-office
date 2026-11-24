import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import connection

from insight.models import (
    BATCH_STATE_KEY,
    BATCH_USER_ANALYSIS_COMPLETED,
    BATCH_USER_ANALYSIS_STARTED,
    UserWeeklyTrend,
    WeeklyTrend,
)
from posts.models import Post, PostDailyStatistics
from scraping.velog.schemas import Post as VelogPost
from users.models import User

KST = ZoneInfo("Asia/Seoul")
# monday fixture(11/23 월 07:05)에 도는 배치. 분석 주차는 11/16(월) 00:00 ~ 11/23(월) 00:00
WEEK_START = datetime(2026, 11, 16, tzinfo=KST)
WEEK_END = datetime(2026, 11, 23, tzinfo=KST)
TUESDAY = datetime(2026, 11, 24, 10, 0, tzinfo=KST)

SKIP_MARKER = "weekly_user_trend_analysis.skipped"
RESULT_FILE = "weekly_analysis_result.txt"

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


def create_weekly_trend(insight: dict | None = None) -> WeeklyTrend:
    """monday 가 속한 주의 공통 분석 행 (11/16 ~ 11/22)"""
    return WeeklyTrend.objects.create(
        week_start_date=WEEK_START.date(),
        week_end_date=(WEEK_END - timedelta(days=1)).date(),
        insight=insight or {},
    )


@pytest.fixture
def create_writer(create_user):
    """이번 주 새 글 1편과 오늘자 통계가 있는 사용자를 만드는 함수"""

    def _create_writer(username: str) -> tuple[User, Post]:
        user = create_user(f"{username}@example.com")
        post = create_post(
            user,
            f"{username} 의 새 글",
            WEEK_START + timedelta(days=2),
            {WEEK_END: (30, 3)},
        )
        return user, post

    return _create_writer


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
def mock_wait(user_trend_module):
    """일일 통계 대기. 진짜는 GitHub 를 조회하며 최대 90분 기다린다. 기본은 모두 모임"""
    with patch.object(
        user_trend_module, "wait_for_daily_stats", return_value=[]
    ) as wait:
        yield wait


@pytest.fixture
def no_leftover_users():
    """트랜잭션으로 감싸지 않는 테스트용. 다른 테스트가 남긴 사용자를 먼저 지운다.

    스크래핑 테스트가 다른 스레드에서 커밋해 남긴 사용자가 있을 수 있고,
    이런 테스트는 끝에서만 DB 를 비운다
    """
    User.objects.all().delete()


@pytest.fixture
def mock_llm():
    with patch(
        "insight.tasks.weekly_user_trend_analysis.analyze_user_posts",
        return_value=LLM_RESULT,
    ) as llm:
        yield llm


@pytest.fixture
def fail_users(user_trend_module):
    """넘긴 사용자의 주간 통계 계산이 예외를 내게 하는 patch 를 만드는 함수"""
    analyzer_cls = user_trend_module.UserWeeklyAnalyzer
    original = analyzer_cls._calculate_user_weekly_total_stats

    def _fail_users(*users: User):
        failing_ids = {user.id for user in users}

        async def calculate(self, user_id, context):
            if user_id in failing_ids:
                raise RuntimeError("stats down")
            return await original(self, user_id, context)

        return patch.object(
            analyzer_cls, "_calculate_user_weekly_total_stats", calculate
        )

    return _fail_users


@pytest.mark.django_db
@pytest.mark.usefixtures("mock_setup_django")
class TestWeeklyUserTrendRun:
    def test_run_saves_trend_per_valid_user_and_reports_expired(
        self,
        user_trend_module,
        monday,
        mock_velog_client_cls,
        mock_llm,
        create_user,
    ):
        """새 글 있는 사용자·없는 사용자는 저장하고, 토큰 만료 사용자는 빼고 보고한다.

        비활성·수신 거부·이메일 없는 사용자는 뉴스레터 대상이 아니므로 분석하지 않는다.
        """
        analyzer_user = user_trend_module.UserWeeklyAnalyzer(
            create_weekly_trend()
        )
        writer = create_user("writer@example.com")
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
        quiet = create_user("quiet@example.com")
        create_post(
            quiet,
            "마지막 글",
            WEEK_END - timedelta(days=13) + timedelta(hours=9),
            {WEEK_START: (10, 1), WEEK_END: (25, 2)},
        )
        # 오늘자 통계가 없으면 토큰 만료로 본다
        expired = create_user("expired@example.com")
        create_post(
            expired,
            "통계가 끊긴 글",
            WEEK_START - timedelta(days=30),
            {WEEK_START: (5, 0)},
        )
        # 뉴스레터 대상이 아닌 사용자
        User.objects.filter(pk=create_user("inactive@example.com").pk).update(
            is_active=False
        )
        User.objects.filter(
            pk=create_user("unsubscribed@example.com").pk
        ).update(newsletter_subscribed=False)
        User.objects.filter(pk=create_user("no-email@example.com").pk).update(
            email=""
        )

        result = async_to_sync(analyzer_user.run)()

        assert result.success is True
        assert result.metadata == {
            "processed_count": 2,
            "expired_token_users": 1,
            "successful_users": 2,
            "failed_users": 0,
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

    def test_run_resumes_only_users_without_this_week_trend(
        self,
        user_trend_module,
        monday,
        mock_velog_client_cls,
        mock_llm,
        create_writer,
    ):
        """이번 주 결과가 이미 있는 사용자는 건너뛰고, 시작·완료 표시를 남긴다"""
        weekly_trend = create_weekly_trend({"trending_summary": []})
        done, _ = create_writer("done")
        UserWeeklyTrend.objects.create(
            user=done,
            week_start_date=weekly_trend.week_start_date,
            week_end_date=weekly_trend.week_end_date,
            insight={"saved": "지난 실행"},
        )
        todo, todo_post = create_writer("todo")

        result = async_to_sync(
            user_trend_module.UserWeeklyAnalyzer(weekly_trend).run
        )()

        assert result.success is True
        assert result.metadata["processed_count"] == 1
        mock_llm.assert_called_once()
        velog_client = mock_velog_client_cls.get_client.return_value
        velog_client.get_post.assert_awaited_once_with(
            str(todo_post.post_uuid)
        )
        assert UserWeeklyTrend.objects.get(user=done).insight == {
            "saved": "지난 실행"
        }
        assert UserWeeklyTrend.objects.filter(user=todo).count() == 1

        weekly_trend.refresh_from_db()
        assert weekly_trend.batch_value(BATCH_USER_ANALYSIS_STARTED)
        assert weekly_trend.batch_value(BATCH_USER_ANALYSIS_COMPLETED)

    def test_run_completes_when_failures_are_under_half(
        self,
        user_trend_module,
        monday,
        mock_velog_client_cls,
        mock_llm,
        create_writer,
        fail_users,
    ):
        """사용자별 실패가 대상의 절반 미만이면 완료 표시를 남기고 실패 수를 보고한다"""
        weekly_trend = create_weekly_trend()
        create_writer("first")
        create_writer("second")
        failed, _ = create_writer("failed")

        with fail_users(failed):
            result = async_to_sync(
                user_trend_module.UserWeeklyAnalyzer(weekly_trend).run
            )()

        assert result.success is True
        assert result.metadata["failed_users"] == 1
        assert result.metadata["successful_users"] == 2
        weekly_trend.refresh_from_db()
        assert weekly_trend.batch_value(BATCH_USER_ANALYSIS_COMPLETED)

    def test_run_counts_users_whose_analysis_or_save_fails(
        self,
        user_trend_module,
        monday,
        mock_velog_client_cls,
        mock_llm,
        create_user,
        create_writer,
    ):
        """분석이나 저장에서 실패한 사용자도 실패 수에 세고, 분석한 수에는 넣지 않는다"""
        weekly_trend = create_weekly_trend()
        for name in ("first", "second", "third"):
            create_writer(name)
        unsaved, _ = create_writer("unsaved")
        # 새 글이 없는 사용자는 분석 단계에서 리마인더를 만든다
        quiet = create_user("quiet@example.com")
        create_post(
            quiet,
            "예전 글",
            WEEK_START - timedelta(days=30),
            {WEEK_START: (5, 0), WEEK_END: (10, 1)},
        )
        create_trend = UserWeeklyTrend.objects.create

        def create(**fields):
            if fields["user_id"] == unsaved.id:
                raise RuntimeError("save down")
            return create_trend(**fields)

        with (
            patch.object(
                UserWeeklyTrend.objects, "create", side_effect=create
            ),
            patch.object(
                user_trend_module.UserWeeklyAnalyzer,
                "_create_user_reminder",
                side_effect=RuntimeError("reminder down"),
            ),
        ):
            result = async_to_sync(
                user_trend_module.UserWeeklyAnalyzer(weekly_trend).run
            )()

        assert result.success is True
        assert result.metadata["failed_users"] == 2
        assert result.metadata["successful_users"] == 3
        assert result.metadata["processed_count"] == 3
        assert UserWeeklyTrend.objects.count() == 3

    def test_run_on_another_day_uses_week_of_weekly_trend(
        self,
        user_trend_module,
        mock_velog_client_cls,
        mock_llm,
        create_user,
        create_writer,
    ):
        """다른 날 다시 돌려도 주차는 오늘이 아니라 공통 분석 행에서 정한다.

        그 주차의 결과가 있는 사용자는 다시 분석하지 않고, 새 사용자는 그 주차와
        주차 다음 날(월) 00:00 의 통계로 저장한다.
        """
        weekly_trend = create_weekly_trend()
        done, _ = create_writer("done")
        UserWeeklyTrend.objects.create(
            user=done,
            week_start_date=weekly_trend.week_start_date,
            week_end_date=weekly_trend.week_end_date,
            insight={"saved": "지난 실행"},
        )
        user = create_user("rerun@example.com")
        create_post(
            user,
            "예전 글",
            WEEK_START - timedelta(days=30),
            {
                WEEK_START: (100, 10),
                WEEK_END: (150, 12),
                WEEK_END + timedelta(days=1): (900, 90),
            },
        )

        # 한 주가 지난 다음 주 화요일
        with patch(
            "utils.utils.get_local_now",
            return_value=TUESDAY + timedelta(days=7),
        ):
            result = async_to_sync(
                user_trend_module.UserWeeklyAnalyzer(weekly_trend).run
            )()

        assert result.success is True
        # 새 글이 있는 done 을 다시 분석하지 않았다
        mock_llm.assert_not_called()
        assert UserWeeklyTrend.objects.get(user=done).insight == {
            "saved": "지난 실행"
        }
        row = UserWeeklyTrend.objects.get(user=user)
        assert row.week_start_date == weekly_trend.week_start_date
        assert row.week_end_date == weekly_trend.week_end_date
        assert row.processed_at == WEEK_END
        assert row.insight["user_weekly_stats"] == {
            "posts": 1,
            "new_posts": 0,
            "views": 50,
            "likes": 2,
        }


@pytest.mark.django_db
@pytest.mark.usefixtures("monday")
class TestWeeklyUserTrendMain:
    def test_main_fails_when_this_week_weekly_trend_is_missing(
        self,
        user_trend_module,
        work_dir,
        mock_wait,
        mock_velog_client_cls,
        mock_llm,
        create_writer,
    ):
        """이번 주 공통 분석 행이 없으면 아무것도 부르지 않고 실패로 끝낸다"""
        # 지난주 행만 있다
        WeeklyTrend.objects.create(
            week_start_date=(WEEK_START - timedelta(days=7)).date(),
            week_end_date=(WEEK_START - timedelta(days=1)).date(),
        )
        create_writer("writer")

        exit_code = async_to_sync(user_trend_module.main)()

        assert exit_code == 1
        result_text = (work_dir / RESULT_FILE).read_text()
        assert "❌ 사용자 주간 분석 실패" in result_text
        assert "이번 주 공통 분석 결과가 없음" in result_text
        mock_wait.assert_not_called()
        mock_velog_client_cls.get_client.assert_not_called()
        mock_llm.assert_not_called()
        assert UserWeeklyTrend.objects.count() == 0

    def test_main_skips_when_user_analysis_is_already_completed(
        self,
        user_trend_module,
        work_dir,
        mock_wait,
        mock_velog_client_cls,
        mock_llm,
        create_writer,
    ):
        """완료 표시가 있으면 기다리지도, velog·LLM 을 부르지도 않고 건너뜀 표시를 남긴다"""
        create_weekly_trend(
            {
                BATCH_STATE_KEY: {
                    BATCH_USER_ANALYSIS_COMPLETED: "2026-11-23T07:40:00+09:00"
                }
            }
        )
        create_writer("writer")

        exit_code = async_to_sync(user_trend_module.main)()

        assert exit_code == 0
        assert (
            "⏭ 사용자 주간 분석 건너뜀" in (work_dir / RESULT_FILE).read_text()
        )
        assert (work_dir / SKIP_MARKER).exists()
        mock_wait.assert_not_called()
        mock_velog_client_cls.get_client.assert_not_called()
        mock_llm.assert_not_called()
        assert UserWeeklyTrend.objects.count() == 0

    # 기다리기 전에 DB 연결을 진짜로 닫으므로 테스트를 트랜잭션으로 감싸지 않는다
    @pytest.mark.django_db(transaction=True)
    def test_main_analyzes_and_writes_result_line(
        self,
        no_leftover_users,
        user_trend_module,
        work_dir,
        mock_wait,
        mock_velog_client_cls,
        mock_llm,
        create_writer,
    ):
        """이번 주 행이 있고 완료 전이면 일일 통계를 기다린 뒤 분석하고 결과 줄을 남긴다"""
        create_weekly_trend()
        writer, _ = create_writer("writer")

        exit_code = async_to_sync(user_trend_module.main)()

        assert exit_code == 0
        mock_wait.assert_called_once()
        assert (
            "✅ 사용자 주간 분석 완료: 성공 1명, 토큰 만료 0명, 실패 0명"
            in (work_dir / RESULT_FILE).read_text().splitlines()
        )
        assert not (work_dir / SKIP_MARKER).exists()
        assert UserWeeklyTrend.objects.filter(user=writer).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_main_fails_without_completion_when_half_of_users_fail(
        self,
        no_leftover_users,
        user_trend_module,
        work_dir,
        mock_wait,
        mock_velog_client_cls,
        mock_llm,
        create_writer,
        fail_users,
    ):
        """사용자별 실패가 이번 실행 대상의 절반이면 완료 표시 없이 실패하고 실패 수를 남긴다"""
        weekly_trend = create_weekly_trend()
        create_writer("writer")
        failed, _ = create_writer("failed")

        with fail_users(failed):
            exit_code = async_to_sync(user_trend_module.main)()

        assert exit_code == 1
        assert "실패 1명" in (work_dir / RESULT_FILE).read_text()
        weekly_trend.refresh_from_db()
        assert weekly_trend.batch_value(BATCH_USER_ANALYSIS_COMPLETED) is None

    @pytest.mark.django_db(transaction=True)
    def test_main_waits_for_stats_of_day_after_week_on_rerun_and_reports_missing_sets(
        self, no_leftover_users, user_trend_module, work_dir, mock_wait
    ):
        """화요일에 다시 돌려도 오늘이 아니라 주차 다음 날(월) 00:00 의 일일 통계를 기다린다.

        기다려도 완료를 확인하지 못한 세트는 결과 파일에 경고로 남긴다.
        GitHub 조회가 실패해도 같은 목록이 오므로 미완료라고 단정하지 않는다.
        """
        create_weekly_trend()
        mock_wait.return_value = [3, 7]

        with patch("utils.utils.get_local_now", return_value=TUESDAY):
            exit_code = async_to_sync(user_trend_module.main)()

        assert exit_code == 0
        assert mock_wait.call_args.args[0] == WEEK_END
        assert (
            "경고: 일일 통계 세트 [3, 7] 완료를 확인하지 못함(미완료 또는 GitHub 조회 실패) — 그 세트 사용자는 토큰 만료로 분류됐을 수 있음"
            in (work_dir / RESULT_FILE).read_text().splitlines()
        )

    @pytest.mark.django_db(transaction=True)
    def test_main_succeeds_when_result_file_cannot_be_written(
        self, no_leftover_users, user_trend_module, work_dir, mock_wait
    ):
        """결과 파일을 못 써도(디스크 가득 등) 세트 경고 줄 때문에 실패로 끝나지 않는다"""
        create_weekly_trend()
        mock_wait.return_value = [3]
        # 같은 이름의 폴더가 있으면 파일 열기가 모두 실패한다
        (work_dir / RESULT_FILE).mkdir()

        exit_code = async_to_sync(user_trend_module.main)()

        assert exit_code == 0

    @pytest.mark.django_db(transaction=True)
    def test_main_skips_when_completed_while_waiting(
        self,
        no_leftover_users,
        user_trend_module,
        work_dir,
        mock_wait,
        mock_velog_client_cls,
        mock_llm,
        create_writer,
    ):
        """기다리는 사이 겹친 실행이 분석을 끝냈으면 분석하지 않고 건너뜀 표시를 남긴다"""
        weekly_trend = create_weekly_trend()
        create_writer("writer")

        def finish_while_waiting(*args):
            WeeklyTrend.objects.get(pk=weekly_trend.pk).mark_batch(
                BATCH_USER_ANALYSIS_COMPLETED
            )
            # 대기는 다른 스레드에서 돌므로 그 스레드의 연결을 닫는다
            connection.close()

        mock_wait.side_effect = finish_while_waiting

        exit_code = async_to_sync(user_trend_module.main)()

        assert exit_code == 0
        assert (work_dir / SKIP_MARKER).exists()
        mock_velog_client_cls.get_client.assert_not_called()
        mock_llm.assert_not_called()
        assert UserWeeklyTrend.objects.count() == 0
