"""Tests for hub.forms — SignupForm, LoginForm, DisplayNameForm."""

import pytest

from hub.forms import DisplayNameForm, SignupForm

from .factories import UserFactory

pytestmark = pytest.mark.django_db


class TestSignupForm:
    def test_valid_form(self):
        form = SignupForm(
            data={
                "email": "new@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            }
        )
        assert form.is_valid()

    def test_password_mismatch(self):
        form = SignupForm(
            data={
                "email": "new@test.com",
                "password": "securepass1",
                "password_confirm": "different",
            }
        )
        assert not form.is_valid()
        assert "password_confirm" in form.errors

    def test_password_too_short(self):
        form = SignupForm(
            data={
                "email": "new@test.com",
                "password": "short",
                "password_confirm": "short",
            }
        )
        assert not form.is_valid()
        assert "password" in form.errors

    def test_duplicate_email(self):
        UserFactory(email="taken@test.com")
        form = SignupForm(
            data={
                "email": "Taken@Test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            }
        )
        assert not form.is_valid()
        assert "email" in form.errors

    def test_email_lowercased(self):
        form = SignupForm(
            data={
                "email": "UPPER@TEST.COM",
                "password": "securepass1",
                "password_confirm": "securepass1",
            }
        )
        assert form.is_valid()
        assert form.cleaned_data["email"] == "upper@test.com"

    def test_promo_code_rejects_spaces(self):
        form = SignupForm(
            data={
                "email": "new@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
                "promo_code": "has space",
            }
        )
        assert not form.is_valid()
        assert "promo_code" in form.errors

    def test_promo_code_optional(self):
        form = SignupForm(
            data={
                "email": "new@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            }
        )
        assert form.is_valid()


class TestDisplayNameForm:
    def test_valid_name(self):
        user = UserFactory(display_name="Original")
        form = DisplayNameForm(data={"display_name": "NewName"}, instance=user)
        assert form.is_valid()

    def test_duplicate_name_rejected(self):
        UserFactory(display_name="TakenName")
        other_user = UserFactory(display_name="Other")
        form = DisplayNameForm(data={"display_name": "takenname"}, instance=other_user)
        assert not form.is_valid()
        assert "display_name" in form.errors

    def test_empty_name_returns_none(self):
        user = UserFactory()
        form = DisplayNameForm(data={"display_name": ""}, instance=user)
        assert form.is_valid()
        assert form.cleaned_data["display_name"] is None

    def test_own_name_allowed(self):
        user = UserFactory(display_name="MyName")
        form = DisplayNameForm(data={"display_name": "MyName"}, instance=user)
        assert form.is_valid()
