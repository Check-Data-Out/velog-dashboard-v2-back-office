import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.utils.timezone import now, timedelta

from qrcode.models import QRLoginToken
from qrcode.admin import QRLoginTokenAdmin

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="test1234")


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
def admin_site():
    return AdminSite()


@pytest.fixture
def qr_admin(admin_site):
    return QRLoginTokenAdmin(QRLoginToken, admin_site)


@pytest.mark.django_db
def test_make_used(qr_admin, qr_token_unused):
    qr_admin.make_used(None, QRLoginToken.objects.filter(pk=qr_token_unused.pk))
    qr_token_unused.refresh_from_db()
    assert qr_token_unused.is_used is True


@pytest.mark.django_db
def test_make_unused(qr_admin, qr_token_used):
    qr_admin.make_unused(None, QRLoginToken.objects.filter(pk=qr_token_used.pk))
    qr_token_used.refresh_from_db()
    assert qr_token_used.is_used is False


@pytest.mark.django_db
def test_admin_list_display(qr_admin):
    assert qr_admin.list_display == (
        "token",
        "user",
        "created_at",
        "expires_at",
        "is_used",
        "ip_address",
        "user_agent",
    )


@pytest.mark.django_db
def test_admin_list_filter(qr_admin):
    assert qr_admin.list_filter == ("is_used", "expires_at", "user")


@pytest.mark.django_db
def test_admin_search_fields(qr_admin):
    assert qr_admin.search_fields == ("token", "user__username", "ip_address")


@pytest.mark.django_db
def test_admin_ordering(qr_admin):
    assert qr_admin.ordering == ("-created_at",)


@pytest.mark.django_db
def test_admin_readonly_fields(qr_admin):
    assert qr_admin.readonly_fields == ("token", "created_at")
