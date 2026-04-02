"""Tests for betting/forms.py and website/forms.py."""

import pytest

from nba.betting.forms import DisplayNameForm, PlaceBetForm, PlaceParlayForm
from nba.tests.factories import UserFactory
from nba.website.forms import LoginForm, SignupForm


class TestPlaceBetForm:
    def test_valid_moneyline_bet(self):
        data = {
            "market": "MONEYLINE",
            "selection": "HOME",
            "odds": -150,
            "stake": "50.00",
        }
        form = PlaceBetForm(data)
        assert form.is_valid(), form.errors

    def test_valid_spread_bet_with_line(self):
        data = {
            "market": "SPREAD",
            "selection": "AWAY",
            "odds": -110,
            "line": -3.5,
            "stake": "25.00",
        }
        form = PlaceBetForm(data)
        assert form.is_valid(), form.errors

    def test_stake_below_minimum_rejected(self):
        data = {
            "market": "MONEYLINE",
            "selection": "HOME",
            "odds": -150,
            "stake": "0.25",
        }
        form = PlaceBetForm(data)
        assert not form.is_valid()
        assert "stake" in form.errors

    def test_stake_above_maximum_rejected(self):
        data = {
            "market": "MONEYLINE",
            "selection": "HOME",
            "odds": -150,
            "stake": "999999999.00",
        }
        form = PlaceBetForm(data)
        assert not form.is_valid()
        assert "stake" in form.errors

    def test_invalid_market_rejected(self):
        data = {
            "market": "INVALID",
            "selection": "HOME",
            "odds": -150,
            "stake": "50.00",
        }
        form = PlaceBetForm(data)
        assert not form.is_valid()

    def test_missing_stake_rejected(self):
        data = {
            "market": "MONEYLINE",
            "selection": "HOME",
            "odds": -150,
        }
        form = PlaceBetForm(data)
        assert not form.is_valid()

    def test_line_is_optional(self):
        data = {
            "market": "MONEYLINE",
            "selection": "HOME",
            "odds": -150,
            "stake": "50.00",
        }
        form = PlaceBetForm(data)
        assert form.is_valid()
        assert form.cleaned_data["line"] is None


class TestPlaceParlayForm:
    def test_valid_stake(self):
        form = PlaceParlayForm({"stake": "30.00"})
        assert form.is_valid()

    def test_minimum_stake(self):
        form = PlaceParlayForm({"stake": "0.50"})
        assert form.is_valid()

    def test_stake_below_minimum_rejected(self):
        form = PlaceParlayForm({"stake": "0.10"})
        assert not form.is_valid()
        assert "stake" in form.errors

    def test_stake_above_maximum_rejected(self):
        form = PlaceParlayForm({"stake": "999999999.00"})
        assert not form.is_valid()

    def test_missing_stake_rejected(self):
        form = PlaceParlayForm({})
        assert not form.is_valid()


@pytest.mark.django_db
class TestDisplayNameForm:
    def test_valid_display_name(self):
        user = UserFactory()
        form = DisplayNameForm({"display_name": "CoolUser"}, instance=user)
        assert form.is_valid()

    def test_empty_display_name_returns_none(self):
        user = UserFactory()
        form = DisplayNameForm({"display_name": "  "}, instance=user)
        assert form.is_valid()
        assert form.cleaned_data["display_name"] is None

    def test_duplicate_display_name_rejected(self):
        UserFactory(display_name="TakenName")
        new_user = UserFactory()
        form = DisplayNameForm({"display_name": "TakenName"}, instance=new_user)
        assert not form.is_valid()
        assert "display_name" in form.errors

    def test_case_insensitive_duplicate_rejected(self):
        UserFactory(display_name="TakenName")
        new_user = UserFactory()
        form = DisplayNameForm({"display_name": "takenname"}, instance=new_user)
        assert not form.is_valid()

    def test_same_user_can_keep_own_name(self):
        user = UserFactory(display_name="MyName")
        form = DisplayNameForm({"display_name": "MyName"}, instance=user)
        assert form.is_valid()


@pytest.mark.django_db
class TestSignupForm:
    def test_valid_signup(self):
        data = {
            "email": "new@test.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        form = SignupForm(data)
        assert form.is_valid(), form.errors

    def test_passwords_must_match(self):
        data = {
            "email": "new@test.com",
            "password": "securepass123",
            "password_confirm": "differentpass",
        }
        form = SignupForm(data)
        assert not form.is_valid()
        assert "password_confirm" in form.errors

    def test_duplicate_email_rejected(self):
        existing = UserFactory()
        data = {
            "email": existing.email,
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        form = SignupForm(data)
        assert not form.is_valid()
        assert "email" in form.errors

    def test_email_lowercased(self):
        data = {
            "email": "Test@EXAMPLE.COM",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        form = SignupForm(data)
        assert form.is_valid()
        assert form.cleaned_data["email"] == "test@example.com"

    def test_password_too_short_rejected(self):
        data = {
            "email": "new@test.com",
            "password": "short",
            "password_confirm": "short",
        }
        form = SignupForm(data)
        assert not form.is_valid()

    def test_invalid_email_rejected(self):
        data = {
            "email": "not-an-email",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        form = SignupForm(data)
        assert not form.is_valid()


class TestLoginForm:
    def test_valid_login_form(self):
        form = LoginForm({"email": "user@test.com", "password": "pass"})
        assert form.is_valid()

    def test_missing_email_rejected(self):
        form = LoginForm({"password": "pass"})
        assert not form.is_valid()

    def test_missing_password_rejected(self):
        form = LoginForm({"email": "user@test.com"})
        assert not form.is_valid()
