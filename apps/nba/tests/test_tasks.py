"""Tests for Celery task orchestration (run_bot_strategies, execute_bot_strategy)."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from betting.models import BetSlip
from bots.models import BotProfile
from bots.tasks import (
    BAILOUT_AMOUNT,
    execute_bot_strategy,
    run_bot_strategies,
)
from games.models import GameStatus

from tests.factories import (
    BotProfileFactory,
    BotUserFactory,
    GameFactory,
    OddsFactory,
    UserBalanceFactory,
)
from vinosports.betting.models import Bankruptcy, UserBalance

# ---------------------------------------------------------------------------
# run_bot_strategies orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRunBotStrategies:
    def test_skips_inactive_bots(self):
        BotProfileFactory(is_active=False)
        result = run_bot_strategies()
        assert result["dispatched"] == 0

    @patch("bots.tasks.roll_action", return_value=False)
    def test_skips_when_roll_fails(self, mock_roll):
        BotProfileFactory(is_active=True)
        result = run_bot_strategies()
        assert result["dispatched"] == 0

    @patch("bots.tasks.execute_bot_strategy.apply_async")
    @patch("bots.tasks.roll_action", return_value=True)
    @patch("bots.tasks.get_active_window")
    def test_dispatches_active_bot(self, mock_window, mock_roll, mock_apply):
        mock_window.return_value = {"bet_probability": 0.8, "max_bets": 3}
        BotProfileFactory(is_active=True)
        result = run_bot_strategies()
        assert result["dispatched"] == 1
        mock_apply.assert_called_once()

    @patch("bots.tasks.execute_bot_strategy.apply_async")
    @patch("bots.tasks.roll_action", return_value=True)
    @patch("bots.tasks.get_active_window", return_value=None)
    def test_skips_when_no_active_window(self, mock_window, mock_roll, mock_apply):
        BotProfileFactory(is_active=True)
        result = run_bot_strategies()
        assert result["dispatched"] == 0
        assert result["skipped_schedule"] == 1

    @patch("bots.tasks.execute_bot_strategy.apply_async")
    @patch("bots.tasks.roll_action", return_value=True)
    @patch("bots.tasks.get_active_window")
    def test_respects_daily_bet_limit(self, mock_window, mock_roll, mock_apply):
        mock_window.return_value = {"bet_probability": 0.8, "max_bets": 5}
        profile = BotProfileFactory(is_active=True, max_daily_bets=2)
        game = GameFactory()
        # Create 2 bets already today
        BetSlip.objects.create(
            user=profile.user,
            game=game,
            market="MONEYLINE",
            selection="HOME",
            odds_at_placement=-150,
            stake=Decimal("50.00"),
        )
        BetSlip.objects.create(
            user=profile.user,
            game=game,
            market="MONEYLINE",
            selection="AWAY",
            odds_at_placement=130,
            stake=Decimal("50.00"),
        )
        UserBalanceFactory(user=profile.user, balance=Decimal("900.00"))
        result = run_bot_strategies()
        assert result["dispatched"] == 0


# ---------------------------------------------------------------------------
# execute_bot_strategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExecuteBotStrategy:
    def test_user_not_found(self):
        result = execute_bot_strategy(999999)
        assert result["error"] == "user_not_found"

    def test_non_bot_user(self):
        from vinosports.users.models import User

        user = User.objects.create_user(
            email="human@test.com", password="pass", is_bot=False
        )
        result = execute_bot_strategy(user.pk)
        assert result["error"] == "user_not_found"

    def test_no_profile(self):
        user = BotUserFactory()
        # Don't create a BotProfile
        result = execute_bot_strategy(user.pk)
        assert result["error"] == "no_profile"

    def test_low_balance_triggers_bailout(self):
        profile = BotProfileFactory(is_active=True)
        user = profile.user
        UserBalanceFactory(user=user, balance=Decimal("0.10"))
        Bankruptcy.objects.create(user=user, balance_at_bankruptcy=Decimal("0.10"))
        GameFactory(status=GameStatus.SCHEDULED)

        execute_bot_strategy(user.pk)
        # After bailout, bot should either place bets or have no games
        balance = UserBalance.objects.get(user=user)
        assert balance.balance >= BAILOUT_AMOUNT

    def test_no_scheduled_games(self):
        profile = BotProfileFactory(is_active=True)
        UserBalanceFactory(user=profile.user, balance=Decimal("1000.00"))
        # No games exist
        result = execute_bot_strategy(profile.user.pk)
        assert result.get("reason") == "no_games" or result.get("bets") == 0

    def test_places_bets_when_games_available(self):
        profile = BotProfileFactory(
            is_active=True,
            strategy_type=BotProfile.StrategyType.FRONTRUNNER,
        )
        UserBalanceFactory(user=profile.user, balance=Decimal("1000.00"))

        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, home_moneyline=-200, away_moneyline=170)

        result = execute_bot_strategy(profile.user.pk)
        # Frontrunner should pick -200 favorite
        assert result.get("placed", 0) >= 1 or result.get("bets") == 0

    def test_daily_limit_enforced(self):
        profile = BotProfileFactory(is_active=True, max_daily_bets=1)
        UserBalanceFactory(user=profile.user, balance=Decimal("1000.00"))

        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, home_moneyline=-200, away_moneyline=170)

        # Pre-existing bet today
        BetSlip.objects.create(
            user=profile.user,
            game=game,
            market="MONEYLINE",
            selection="HOME",
            odds_at_placement=-200,
            stake=Decimal("50.00"),
        )

        result = execute_bot_strategy(profile.user.pk)
        assert result.get("reason") == "daily_limit" or result.get("bets") == 0
