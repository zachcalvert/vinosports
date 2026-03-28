"""Tests for EPL featured parlay generation and the FeaturedParlay models."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from vinosports.betting.featured import FeaturedParlay, FeaturedParlayLeg
from vinosports.betting.featured_utils import _fallback, generate_parlay_copy
from vinosports.bots.models import BotProfile, StrategyType

from .factories import (
    MatchFactory,
    OddsFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# FeaturedParlay model
# ---------------------------------------------------------------------------


class TestFeaturedParlayModel:
    def test_create_with_legs(self):
        user = UserFactory(is_bot=True)
        fp = FeaturedParlay.objects.create(
            league="epl",
            sponsor=user,
            title="Weekend Chalk",
            description="Safe picks for the weekend.",
            expires_at=timezone.now() + timedelta(days=1),
            combined_odds=Decimal("6.00"),
            potential_payout=Decimal("60.00"),
        )
        FeaturedParlayLeg.objects.create(
            featured_parlay=fp,
            event_id=1,
            event_label="Arsenal vs Chelsea",
            selection="HOME_WIN",
            selection_label="Home Win",
            odds_snapshot=Decimal("2.00"),
        )
        FeaturedParlayLeg.objects.create(
            featured_parlay=fp,
            event_id=2,
            event_label="Liverpool vs Man City",
            selection="DRAW",
            selection_label="Draw",
            odds_snapshot=Decimal("3.00"),
        )

        assert fp.legs.count() == 2
        assert fp.status == FeaturedParlay.Status.ACTIVE
        assert str(fp) == "Weekend Chalk (EPL) — Active"

    def test_status_choices(self):
        user = UserFactory(is_bot=True)
        fp = FeaturedParlay.objects.create(
            league="nba",
            sponsor=user,
            title="Test",
            expires_at=timezone.now(),
            combined_odds=Decimal("1.00"),
            potential_payout=Decimal("10.00"),
            status=FeaturedParlay.Status.EXPIRED,
        )
        assert fp.status == "EXPIRED"


# ---------------------------------------------------------------------------
# Expiration task
# ---------------------------------------------------------------------------


class TestExpireFeaturedParlays:
    def test_expires_past_due(self):
        from vinosports.betting.tasks import expire_featured_parlays

        user = UserFactory(is_bot=True)
        fp = FeaturedParlay.objects.create(
            league="epl",
            sponsor=user,
            title="Old Parlay",
            expires_at=timezone.now() - timedelta(hours=1),
            combined_odds=Decimal("5.00"),
            potential_payout=Decimal("50.00"),
        )

        expire_featured_parlays()

        fp.refresh_from_db()
        assert fp.status == FeaturedParlay.Status.EXPIRED

    def test_does_not_expire_future(self):
        from vinosports.betting.tasks import expire_featured_parlays

        user = UserFactory(is_bot=True)
        fp = FeaturedParlay.objects.create(
            league="epl",
            sponsor=user,
            title="Future Parlay",
            expires_at=timezone.now() + timedelta(hours=2),
            combined_odds=Decimal("5.00"),
            potential_payout=Decimal("50.00"),
        )

        expire_featured_parlays()

        fp.refresh_from_db()
        assert fp.status == FeaturedParlay.Status.ACTIVE

    def test_skips_already_expired(self):
        from vinosports.betting.tasks import expire_featured_parlays

        user = UserFactory(is_bot=True)
        fp = FeaturedParlay.objects.create(
            league="epl",
            sponsor=user,
            title="Already Expired",
            expires_at=timezone.now() - timedelta(hours=1),
            combined_odds=Decimal("5.00"),
            potential_payout=Decimal("50.00"),
            status=FeaturedParlay.Status.EXPIRED,
        )

        expire_featured_parlays()

        fp.refresh_from_db()
        assert fp.status == FeaturedParlay.Status.EXPIRED


# ---------------------------------------------------------------------------
# Claude copy generation (with mocking)
# ---------------------------------------------------------------------------


class TestGenerateParlayCopy:
    def test_fallback_when_no_api_key(self):
        with patch("vinosports.betting.featured_utils.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = None
            result = generate_parlay_copy([], "epl", "favorites")

        assert result["title"] == "Weekend Chalk"
        assert result["description"] != ""

    def test_fallback_returns_league_specific(self):
        assert _fallback("nba", "favorites")["title"] == "Tonight's Chalk"
        assert _fallback("epl", "underdogs")["title"] == "Underdog Special"
        assert _fallback("nba", "value")["title"] == "Sharp Plays"

    def test_fallback_unknown_theme(self):
        result = _fallback("epl", "nonexistent")
        assert "title" in result


# ---------------------------------------------------------------------------
# EPL generation task
# ---------------------------------------------------------------------------


class TestEPLGenerateFeaturedParlays:
    def _create_bot(self):
        from tests.factories import ScheduleTemplateFactory

        bot_user = UserFactory(is_bot=True, display_name="TestBot")
        UserBalanceFactory(user=bot_user)
        template = ScheduleTemplateFactory()
        BotProfile.objects.create(
            user=bot_user,
            strategy_type=StrategyType.PARLAY,
            is_active=True,
            active_in_epl=True,
            schedule_template=template,
            persona_prompt="Test bot",
        )
        return bot_user

    @patch("vinosports.betting.featured_utils.generate_parlay_copy")
    def test_creates_featured_parlays(self, mock_copy):
        mock_copy.return_value = {
            "title": "Test Parlay",
            "description": "A test description.",
        }
        self._create_bot()

        # Create 4 scheduled matches with odds
        matches = [MatchFactory() for _ in range(4)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("1.80"),
                draw=Decimal("3.50"),
                away_win=Decimal("4.20"),
            )

        from epl.bots.tasks import generate_featured_parlays

        generate_featured_parlays()

        parlays = FeaturedParlay.objects.filter(league="epl")
        assert parlays.count() >= 1

        fp = parlays.first()
        assert fp.title == "Test Parlay"
        assert fp.legs.count() >= 2
        assert fp.status == FeaturedParlay.Status.ACTIVE
        assert fp.combined_odds > Decimal("1.00")

    def test_skips_when_no_matches(self):
        self._create_bot()

        from epl.bots.tasks import generate_featured_parlays

        generate_featured_parlays()

        assert FeaturedParlay.objects.count() == 0

    def test_skips_when_no_bots(self):
        matches = [MatchFactory() for _ in range(3)]
        for m in matches:
            OddsFactory(match=m)

        from epl.bots.tasks import generate_featured_parlays

        generate_featured_parlays()

        assert FeaturedParlay.objects.count() == 0

    @patch("vinosports.betting.featured_utils.generate_parlay_copy")
    def test_each_parlay_has_unique_sponsor(self, mock_copy):
        """Multiple parlays created in one run should each have a different sponsor bot."""
        from tests.factories import ScheduleTemplateFactory

        mock_copy.return_value = {
            "title": "Test Parlay",
            "description": "A test description.",
        }
        # Create 3 bots with unique names so all 3 themes can each get a unique sponsor
        for i in range(3):
            bot_user = UserFactory(is_bot=True)
            UserBalanceFactory(user=bot_user)
            template = ScheduleTemplateFactory()
            BotProfile.objects.create(
                user=bot_user,
                strategy_type=StrategyType.PARLAY,
                is_active=True,
                active_in_epl=True,
                schedule_template=template,
                persona_prompt="Test bot",
            )

        matches = [MatchFactory() for _ in range(4)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("1.80"),
                draw=Decimal("3.50"),
                away_win=Decimal("4.20"),
            )

        from epl.bots.tasks import generate_featured_parlays

        generate_featured_parlays()

        parlays = FeaturedParlay.objects.filter(league="epl")
        assert parlays.count() >= 2

        sponsor_ids = list(parlays.values_list("sponsor_id", flat=True))
        assert len(sponsor_ids) == len(set(sponsor_ids)), (
            "Each featured parlay should have a unique sponsor bot"
        )
