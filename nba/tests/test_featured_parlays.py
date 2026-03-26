"""Tests for NBA featured parlay generation."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from vinosports.betting.featured import FeaturedParlay
from vinosports.bots.models import BotProfile, StrategyType

from .factories import (
    GameFactory,
    OddsFactory,
    ScheduleTemplateFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


class TestNBAGenerateFeaturedParlays:
    def _create_bot(self):
        bot_user = UserFactory(is_bot=True, display_name="NBABot")
        UserBalanceFactory(user=bot_user)
        template = ScheduleTemplateFactory()
        BotProfile.objects.create(
            user=bot_user,
            strategy_type=StrategyType.PARLAY,
            is_active=True,
            active_in_nba=True,
            schedule_template=template,
            persona_prompt="Test NBA bot",
        )
        return bot_user

    @patch("vinosports.betting.featured_utils.generate_parlay_copy")
    @patch("nba.bots.tasks.today_et")
    def test_creates_featured_parlays(self, mock_today, mock_copy):
        from nba.bots.tasks import generate_featured_parlays

        mock_copy.return_value = {
            "title": "Tonight's Favorites",
            "description": "Chalk it up.",
        }
        today = timezone.localdate()
        mock_today.return_value = today

        self._create_bot()

        games = [
            GameFactory(game_date=today, tip_off=timezone.now() + timedelta(hours=6))
            for _ in range(4)
        ]
        for g in games:
            OddsFactory(game=g)

        generate_featured_parlays()

        parlays = FeaturedParlay.objects.filter(league="nba")
        assert parlays.count() >= 1

        fp = parlays.first()
        assert fp.title == "Tonight's Favorites"
        assert fp.legs.count() >= 2
        assert fp.combined_odds > Decimal("1.00")

        # Legs are denormalized
        leg = fp.legs.first()
        assert leg.event_label != ""
        assert leg.selection_label != ""
        assert leg.odds_snapshot > Decimal("0")

    @patch("nba.bots.tasks.today_et")
    def test_skips_when_no_games(self, mock_today):
        from nba.bots.tasks import generate_featured_parlays

        mock_today.return_value = timezone.localdate()
        self._create_bot()

        generate_featured_parlays()

        assert FeaturedParlay.objects.count() == 0

    @patch("nba.bots.tasks.today_et")
    def test_skips_when_no_bots(self, mock_today):
        from nba.bots.tasks import generate_featured_parlays

        today = timezone.localdate()
        mock_today.return_value = today
        games = [GameFactory(game_date=today) for _ in range(3)]
        for g in games:
            OddsFactory(game=g)

        generate_featured_parlays()

        assert FeaturedParlay.objects.count() == 0

    @patch("vinosports.betting.featured_utils.generate_parlay_copy")
    @patch("nba.bots.tasks.today_et")
    def test_leg_extras_stored(self, mock_today, mock_copy):
        from nba.bots.tasks import generate_featured_parlays

        mock_copy.return_value = {"title": "Spread Special", "description": ""}
        today = timezone.localdate()
        mock_today.return_value = today

        self._create_bot()

        games = [
            GameFactory(game_date=today, tip_off=timezone.now() + timedelta(hours=6))
            for _ in range(4)
        ]
        for g in games:
            OddsFactory(game=g, spread_home=-110, spread_line=-3.5)

        generate_featured_parlays()

        # At least the favorites theme should have been created
        assert FeaturedParlay.objects.count() >= 1
