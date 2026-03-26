"""Tests for vinosports.users — User model and UserManager."""

import pytest

from vinosports.users.models import User

from .factories import UserFactory

pytestmark = pytest.mark.django_db


class TestUserManager:
    def test_create_user(self):
        user = User.objects.create_user(email="test@example.com", password="pass123")
        assert user.email == "test@example.com"
        assert user.check_password("pass123")
        assert not user.is_staff
        assert not user.is_superuser

    def test_create_user_normalizes_email(self):
        user = User.objects.create_user(email="Test@EXAMPLE.com", password="pass123")
        assert user.email == "Test@example.com"

    def test_create_user_requires_email(self):
        with pytest.raises(ValueError, match="Email"):
            User.objects.create_user(email="", password="pass123")

    def test_create_superuser(self):
        user = User.objects.create_superuser(email="admin@test.com", password="pass123")
        assert user.is_staff
        assert user.is_superuser

    def test_create_superuser_rejects_non_staff(self):
        with pytest.raises(ValueError, match="is_staff"):
            User.objects.create_superuser(
                email="admin@test.com", password="pass123", is_staff=False
            )

    def test_create_superuser_rejects_non_superuser(self):
        with pytest.raises(ValueError, match="is_superuser"):
            User.objects.create_superuser(
                email="admin@test.com", password="pass123", is_superuser=False
            )


class TestUserModel:
    def test_id_hash_auto_generated(self):
        user = UserFactory()
        assert len(user.id_hash) == 8
        assert user.id_hash.isalnum()

    def test_slug_auto_generated_from_display_name(self):
        user = UserFactory(display_name="Cool Player")
        assert user.slug.startswith("cool-player-")
        assert user.id_hash in user.slug

    def test_slug_generated_from_email_when_no_display_name(self):
        user = UserFactory(display_name=None, email="jane@example.com")
        assert user.slug.startswith("jane-")

    def test_slug_updates_on_display_name_change(self):
        user = UserFactory(display_name="OldName")
        old_slug = user.slug
        user.display_name = "NewName"
        user.save()
        assert user.slug != old_slug
        assert user.slug.startswith("newname-")

    def test_slug_stable_when_display_name_unchanged(self):
        user = UserFactory(display_name="Stable")
        slug = user.slug
        user.save()
        assert user.slug == slug

    def test_str_returns_email(self):
        user = UserFactory(email="show@test.com")
        assert str(user) == "show@test.com"

    def test_username_field_is_email(self):
        assert User.USERNAME_FIELD == "email"
