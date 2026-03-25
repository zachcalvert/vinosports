"""Tests for bot bet placement service."""

from decimal import Decimal

import pytest

from nba.activity.models import ActivityEvent
from nba.betting.models import BetSlip, Parlay
from nba.bots.services import _place_parlay, _place_single_bet, place_bot_bets
from nba.bots.strategies import BetInstruction, ParlayInstruction
from nba.tests.factories import (
    BotUserFactory,
    GameFactory,
    UserBalanceFactory,
)
from vinosports.betting.models import UserBalance


@pytest.mark.django_db
class TestPlaceSingleBet:
    def test_creates_betslip_and_deducts_balance(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()

        instr = BetInstruction(
            game_id=game.pk,
            market="MONEYLINE",
            selection="HOME",
            line=None,
            odds=-150,
            stake=Decimal("50.00"),
        )

        ok = _place_single_bet(user, instr)

        assert ok is True
        assert BetSlip.objects.filter(user=user, game=game).exists()

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("450.00")

    def test_insufficient_balance_skips(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("10.00"))
        game = GameFactory()

        instr = BetInstruction(
            game_id=game.pk,
            market="MONEYLINE",
            selection="HOME",
            line=None,
            odds=-150,
            stake=Decimal("50.00"),
        )

        ok = _place_single_bet(user, instr)

        assert ok is False
        assert not BetSlip.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestPlaceParlay:
    def test_creates_parlay_with_legs(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()
        g2 = GameFactory()

        instr = ParlayInstruction(
            legs=[
                BetInstruction(
                    game_id=g1.pk,
                    market="MONEYLINE",
                    selection="HOME",
                    line=None,
                    odds=-150,
                    stake=Decimal("0"),
                ),
                BetInstruction(
                    game_id=g2.pk,
                    market="MONEYLINE",
                    selection="AWAY",
                    line=None,
                    odds=130,
                    stake=Decimal("0"),
                ),
            ],
            stake=Decimal("30.00"),
        )

        ok = _place_parlay(user, instr)

        assert ok is True
        assert Parlay.objects.filter(user=user).exists()
        parlay = Parlay.objects.get(user=user)
        assert parlay.legs.count() == 2

    def test_rejects_single_leg(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()

        instr = ParlayInstruction(
            legs=[
                BetInstruction(
                    game_id=g1.pk,
                    market="MONEYLINE",
                    selection="HOME",
                    line=None,
                    odds=-150,
                    stake=Decimal("0"),
                ),
            ],
            stake=Decimal("30.00"),
        )

        ok = _place_parlay(user, instr)
        assert ok is False

    def test_max_payout_capped(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("5000.00"))
        g1 = GameFactory()
        g2 = GameFactory()

        instr = ParlayInstruction(
            legs=[
                BetInstruction(
                    game_id=g1.pk,
                    market="MONEYLINE",
                    selection="HOME",
                    line=None,
                    odds=500,
                    stake=Decimal("0"),
                ),
                BetInstruction(
                    game_id=g2.pk,
                    market="MONEYLINE",
                    selection="HOME",
                    line=None,
                    odds=500,
                    stake=Decimal("0"),
                ),
            ],
            stake=Decimal("1000.00"),
        )

        ok = _place_parlay(user, instr)
        assert ok is True
        parlay = Parlay.objects.get(user=user)
        assert parlay.max_payout <= Decimal("10000.00")

    def test_insufficient_balance_skips(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("10.00"))
        g1 = GameFactory()
        g2 = GameFactory()

        instr = ParlayInstruction(
            legs=[
                BetInstruction(
                    game_id=g1.pk,
                    market="MONEYLINE",
                    selection="HOME",
                    line=None,
                    odds=-150,
                    stake=Decimal("0"),
                ),
                BetInstruction(
                    game_id=g2.pk,
                    market="MONEYLINE",
                    selection="AWAY",
                    line=None,
                    odds=130,
                    stake=Decimal("0"),
                ),
            ],
            stake=Decimal("50.00"),
        )

        ok = _place_parlay(user, instr)
        assert ok is False


@pytest.mark.django_db
class TestPlaceBotBets:
    def test_mixed_instructions(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        g3 = GameFactory()

        instructions = [
            BetInstruction(
                game_id=g1.pk,
                market="MONEYLINE",
                selection="HOME",
                line=None,
                odds=-150,
                stake=Decimal("50.00"),
            ),
            ParlayInstruction(
                legs=[
                    BetInstruction(
                        game_id=g2.pk,
                        market="MONEYLINE",
                        selection="HOME",
                        line=None,
                        odds=-150,
                        stake=Decimal("0"),
                    ),
                    BetInstruction(
                        game_id=g3.pk,
                        market="MONEYLINE",
                        selection="AWAY",
                        line=None,
                        odds=130,
                        stake=Decimal("0"),
                    ),
                ],
                stake=Decimal("30.00"),
            ),
        ]

        result = place_bot_bets(user, instructions)
        assert result["placed"] == 2
        assert result["skipped"] == 0

    def test_creates_activity_events(self):
        user = BotUserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()

        instructions = [
            BetInstruction(
                game_id=game.pk,
                market="MONEYLINE",
                selection="HOME",
                line=None,
                odds=-150,
                stake=Decimal("50.00"),
            ),
        ]

        place_bot_bets(user, instructions)
        event = ActivityEvent.objects.get(event_type=ActivityEvent.EventType.BOT_BET)
        assert event.url == game.get_absolute_url()
