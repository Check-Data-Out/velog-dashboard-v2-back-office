import pytest
from django.contrib.admin.sites import AdminSite
from django.utils.timezone import now, timedelta

from users.admin import QRLoginTokenAdmin, UserAdmin
from users.models import QRLoginToken, User


@pytest.fixture
def qr_token_unused(user, db):
    return QRLoginToken.objects.create(
        token="TOKEN123",
        user=user,
        expires_at=now() + timedelta(minutes=5),
        is_used=False,
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )


@pytest.fixture
def qr_token_used(user, db):
    return QRLoginToken.objects.create(
        token="TOKEN456",
        user=user,
        expires_at=now() + timedelta(minutes=5),
        is_used=True,
        ip_address="192.168.1.2",
        user_agent="Mozilla/5.0",
    )


@pytest.fixture
def qr_admin(admin_site):
    return QRLoginTokenAdmin(QRLoginToken, admin_site)


@pytest.mark.django_db
def test_make_used(qr_admin, qr_token_unused):
    qr_admin.make_used(
        None, QRLoginToken.objects.filter(pk=qr_token_unused.pk)
    )
    qr_token_unused.refresh_from_db()
    assert qr_token_unused.is_used is True


@pytest.mark.django_db
def test_make_unused(qr_admin, qr_token_used):
    qr_admin.make_unused(
        None, QRLoginToken.objects.filter(pk=qr_token_used.pk)
    )
    qr_token_used.refresh_from_db()
    assert qr_token_used.is_used is False


@pytest.mark.django_db
def test_admin_list_display(qr_admin):
    assert qr_admin.list_display == (
        "token",
        "user_link",
        "created_at",
        "expires_at",
        "is_used",
        "ip_address",
        "user_agent",
    )


@pytest.mark.django_db
def test_admin_list_filter(qr_admin):
    assert qr_admin.list_filter == ("is_used", "expires_at")


@pytest.mark.django_db
def test_admin_search_fields(qr_admin):
    assert qr_admin.search_fields == ("token", "ip_address")


@pytest.mark.django_db
def test_admin_ordering(qr_admin):
    assert qr_admin.ordering == ("-id",)


@pytest.mark.django_db
def test_admin_readonly_fields(qr_admin):
    assert qr_admin.readonly_fields == ("token", "created_at")


@pytest.mark.django_db
def test_qr_login_token_n_plus_one(django_assert_num_queries, user):
    """QRLoginToken 조회 시 N+1 문제가 없는지 테스트"""

    QRLoginToken.objects.bulk_create(
        [
            QRLoginToken(
                token=f"TOKEN{i}",
                user=user,
                expires_at=now() + timedelta(minutes=5),
                is_used=False,
            )
            for i in range(5)
        ]
    )

    admin_site = AdminSite()
    user_admin = UserAdmin(User, admin_site)

    with django_assert_num_queries(2):
        qs = user_admin.get_queryset(None)
        users = list(qs)

        assert hasattr(users[0], "prefetched_qr_tokens")

    assert len(users[0].prefetched_qr_tokens) == 5
