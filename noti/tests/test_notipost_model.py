import pytest
from django.contrib.auth import get_user_model

from noti.models import NotiPost

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def noti_post(user, db):
    return NotiPost.objects.create(
        title="Test Title",
        content="Test Content",
        author=user,
    )


@pytest.mark.django_db
def test_noti_post_creation(noti_post):
    assert noti_post.title == "Test Title"
    assert noti_post.content == "Test Content"
    assert noti_post.is_active is True
    assert noti_post.created_at is not None
    assert noti_post.updated_at is not None


@pytest.mark.django_db
def test_noti_post_deactivate(noti_post):
    noti_post.deactivate()
    assert noti_post.is_active is False


@pytest.mark.django_db
def test_noti_post_activate(noti_post):
    noti_post.is_active = False
    noti_post.activate()
    assert noti_post.is_active is True


@pytest.mark.django_db
def test_noti_post_str(noti_post):
    assert str(noti_post) == f"[{noti_post.pk}] {noti_post.title}"
