"""Phase 4 — RequestLifecycleService 테스트."""

import uuid

import pytest

from ops_tracking.models import StatsRefreshRequest, StatsRefreshRequestStatus
from ops_tracking.services import RequestLifecycleService
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="tok",
        refresh_token="tok",
        group_id=1,
        email="ops-svc@example.com",
        username="ops-svc",
        is_active=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="tok",
        refresh_token="tok",
        group_id=1,
        email="ops-admin@example.com",
        username="ops-admin",
        is_active=True,
    )


@pytest.fixture
def service():
    return RequestLifecycleService()


class TestMarkQueued:
    def test_creates_row_with_queued_status(self, service, user, admin_user):
        rid = str(uuid.uuid4())
        obj = service.mark_queued(rid, user.id, admin_user.id)
        assert str(obj.request_id) == rid
        assert obj.status == StatsRefreshRequestStatus.QUEUED
        assert obj.user_id == user.id
        assert obj.requested_by_id == admin_user.id
        assert StatsRefreshRequest.objects.count() == 1

    def test_mark_queued_is_idempotent_with_same_request_id(
        self, service, user
    ):
        rid = str(uuid.uuid4())
        service.mark_queued(rid, user.id, None)
        service.mark_queued(rid, user.id, None)  # 두 번 호출해도 행 1개
        assert StatsRefreshRequest.objects.count() == 1


class TestMarkProcessingSuccessFailed:
    def test_processing_success_transition(self, service, user):
        rid = str(uuid.uuid4())
        service.mark_queued(rid, user.id, None)
        service.mark_processing(rid, retry_count=0)
        obj = service.mark_success(rid)
        assert obj.status == StatsRefreshRequestStatus.SUCCESS
        assert obj.finished_at is not None

    def test_mark_failed_truncates_error_to_2000(self, service, user):
        rid = str(uuid.uuid4())
        service.mark_queued(rid, user.id, None)
        long_err = "x" * 3000
        obj = service.mark_failed(rid, long_err, retry_count=1)
        assert obj.status == StatsRefreshRequestStatus.FAILED
        assert len(obj.last_error) == 2000

    def test_mark_dlq_sets_status_and_finished_at(self, service, user):
        rid = str(uuid.uuid4())
        service.mark_queued(rid, user.id, None)
        obj = service.mark_dlq(rid, error="poison pill", reclaimed_count=3)
        assert obj.status == StatsRefreshRequestStatus.DLQ
        assert obj.reclaimed_count == 3
        assert obj.finished_at is not None

    def test_mark_processing_returns_none_when_row_missing(self, service):
        rid = str(uuid.uuid4())
        assert service.mark_processing(rid) is None


class TestHasInflightForUsers:
    def test_detects_queued_and_processing_as_inflight(self, service, user):
        rid_q = str(uuid.uuid4())
        rid_p = str(uuid.uuid4())
        service.mark_queued(rid_q, user.id, None)
        service.mark_queued(rid_p, user.id, None)
        service.mark_processing(rid_p)

        inflight = service.has_inflight_for_users([user.id])
        assert inflight == {user.id}

    def test_ignores_success_and_failed(self, service, user):
        rid = str(uuid.uuid4())
        service.mark_queued(rid, user.id, None)
        service.mark_processing(rid)
        service.mark_success(rid)
        assert service.has_inflight_for_users([user.id]) == set()

    def test_empty_input_returns_empty_set(self, service):
        assert service.has_inflight_for_users([]) == set()
