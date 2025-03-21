import uuid
from datetime import timedelta

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User as DjangoUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpRequest
from django.test import Client
from django.utils.timezone import now

from users.admin import UserAdmin
from users.models import QRLoginToken, User


@pytest.fixture
def db_admin_user(db):
    """Admin 유저 생성 (Django 기본 User 모델)"""
    return DjangoUser.objects.create_superuser(
        username="admin", email="admin@example.com", password="adminpassword"
    )


@pytest.fixture
def client_logged_in(db_admin_user):
    """Admin 유저로 로그인한 Django 테스트 클라이언트"""
    client = Client()
    client.force_login(db_admin_user)
    return client


@pytest.fixture
def user(db):
    """일반 User 객체 생성"""
    return User.objects.create(
        velog_uuid=uuid.uuid4(),
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        group_id=1,
        email="test@example.com",
        is_active=True,
    )


@pytest.fixture
def admin_site():
    """Django AdminSite 인스턴스"""
    return AdminSite()


@pytest.fixture
def user_admin(admin_site):
    """UserAdmin 인스턴스"""
    return UserAdmin(User, admin_site)


@pytest.fixture
def request_with_messages(db_admin_user):
    """Admin 유저 로그인된 request 객체"""
    request = HttpRequest()
    setattr(request, "session", {})
    setattr(request, "user", db_admin_user)  # ✅ Admin User 설정
    messages_storage = FallbackStorage(request)
    setattr(request, "_messages", messages_storage)
    return request


@pytest.fixture
def qr_login_token(db, user):
    return QRLoginToken.objects.create(
        token="test_token",
        user=user,
        expires_at=now() + timedelta(minutes=5),
        is_used=False,
    )
