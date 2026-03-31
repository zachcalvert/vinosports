"""Tests for the bot bet placement service."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from nfl.betting.models import BetSlip, Parlay, ParlayLeg
from nfl.bots.services import place_bot_bets
from nfl.bots.strategies import BetInstruction, ParlayInstruction
from nfl.tests.factories import (
    GameFactory,
    TeamFactory,
    UserBalanceFactory,
    UserFactory,
)

# NFL URLs aren't wired yet (Phase 4), so mock get_absolute_url
_mock_url = patch(
    "nfl.games.models.Game.get_absolute_url", return_value="/nfl/games/test/"
)


@pytest.fixture
def bot_user(db):
    user = UserFactory(is_bot=True, display_name="TestBot")
    UserBalanceFactory(user=user, balance=Decimal("1000.00"))
    return user


@pytest.fixture
def game_with_teams(db):
    home = TeamFactory(abbreviation="KC", short_name="Chiefs")
    away = TeamFactory(abbreviation="BUF", short_name="Bills")
    game = GameFactory(home_team=home, away_team=away)
    return game


@pytest.mark.django_db
class TestPlaceBotBets:
    @_mock_url
    def test_places_single_bet(self, _mock, bot_user, game_with_teams):
        instr = BetInstruction(
            game_id=game_with_teams.pk,
            market="MONEYLINE",
            selection="HOME",
            line=None,
            odds=-150,
            stake=Decimal("50.00"),
        )
        result = place_bot_bets(bot_user, [instr])
        assert result == {"placed": 1, "skipped": 0}
        assert BetSlip.objects.filter(user=bot_user).count() == 1

    @_mock_url
    def test_places_parlay(self, _mock, bot_user):
        game1 = GameFactory()
        game2 = GameFactory()
        legs = [
            BetInstruction(
                game_id=game1.pk,
                market="MONEYLINE",
                selection="HOME",
                line=None,
                odds=-150,
                stake=Decimal("0"),
            ),
            BetInstruction(
                game_id=game2.pk,
                market="MONEYLINE",
                selection="AWAY",
                line=None,
                odds=130,
                stake=Decimal("0"),
            ),
        ]
        instr = ParlayInstruction(legs=legs, stake=Decimal("30.00"))
        result = place_bot_bets(bot_user, [instr])
        assert result == {"placed": 1, "skipped": 0}
        assert Parlay.objects.filter(user=bot_user).count() == 1
        assert ParlayLeg.objects.count() == 2

    def test_skips_bet_on_insufficient_balance(self, bot_user, game_with_teams):
        from vinosports.betting.models import UserBalance

        UserBalance.objects.filter(user=bot_user).update(balance=Decimal("0.00"))

        instr = BetInstruction(
            game_id=game_with_teams.pk,
            market="MONEYLINE",
            selection="HOME",
            line=None,
            odds=-150,
            stake=Decimal("50.00"),
        )
        result = place_bot_bets(bot_user, [instr])
        assert result == {"placed": 0, "skipped": 1}
        assert BetSlip.objects.filter(user=bot_user).count() == 0

    @_mock_url
    def test_places_multiple_bets_independently(self, _mock, bot_user):
        game1 = GameFactory()
        game2 = GameFactory()
        instructions = [
            BetInstruction(
                game_id=game1.pk,
                market="MONEYLINE",
                selection="HOME",
                line=None,
                odds=-130,
                stake=Decimal("50.00"),
            ),
            BetInstruction(
                game_id=game2.pk,
                market="SPREAD",
                selection="AWAY",
                line=3.0,
                odds=-110,
                stake=Decimal("50.00"),
            ),
        ]
        result = place_bot_bets(bot_user, instructions)
        assert result == {"placed": 2, "skipped": 0}
        assert BetSlip.objects.filter(user=bot_user).count() == 2

    def test_parlay_with_single_leg_skipped(self, bot_user):
        game1 = GameFactory()
        instr = ParlayInstruction(
            legs=[
                BetInstruction(
                    game_id=game1.pk,
                    market="MONEYLINE",
                    selection="HOME",
                    line=None,
                    odds=-150,
                    stake=Decimal("0"),
                ),
            ],
            stake=Decimal("30.00"),
        )
        result = place_bot_bets(bot_user, [instr])
        assert result == {"placed": 0, "skipped": 1}

    @_mock_url
    def test_creates_activity_event_for_single_bet(
        self, _mock, bot_user, game_with_teams
    ):
        from nfl.activity.models import ActivityEvent

        instr = BetInstruction(
            game_id=game_with_teams.pk,
            market="MONEYLINE",
            selection="HOME",
            line=None,
            odds=-150,
            stake=Decimal("50.00"),
        )
        place_bot_bets(bot_user, [instr])
        assert (
            ActivityEvent.objects.filter(
                event_type=ActivityEvent.EventType.BOT_BET
            ).count()
            == 1
        )

    @_mock_url
    def test_creates_activity_event_for_parlay(self, _mock, bot_user):
        from nfl.activity.models import ActivityEvent

        game1 = GameFactory()
        game2 = GameFactory()
        legs = [
            BetInstruction(
                game_id=game1.pk,
                market="MONEYLINE",
                selection="HOME",
                line=None,
                odds=-150,
                stake=Decimal("0"),
            ),
            BetInstruction(
                game_id=game2.pk,
                market="MONEYLINE",
                selection="AWAY",
                line=None,
                odds=130,
                stake=Decimal("0"),
            ),
        ]
        instr = ParlayInstruction(legs=legs, stake=Decimal("30.00"))
        place_bot_bets(bot_user, [instr])
        assert (
            ActivityEvent.objects.filter(
                event_type=ActivityEvent.EventType.BOT_BET
            ).count()
            == 1
        )
