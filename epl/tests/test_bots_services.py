"""Tests for epl.bots.services — bet placement, odds helpers, and balance top-ups."""

from decimal import Decimal

import pytest

from epl.betting.models import ParlayLeg
from epl.bots.services import (
    get_available_matches_for_bot,
    get_best_odds_map,
    get_full_odds_map,
    maybe_topup_bot,
    place_bot_bet,
    place_bot_parlay,
)
from epl.matches.models import Match
from epl.tests.factories import (
    BetSlipFactory,
    BotUserFactory,
    MatchFactory,
    OddsFactory,
    ParlayFactory,
    ParlayLegFactory,
    UserBalanceFactory,
)
from vinosports.betting.models import Bailout, Bankruptcy, UserBalance

# ---------------------------------------------------------------------------
# get_available_matches_for_bot
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetAvailableMatchesForBot:
    def test_returns_scheduled_matches(self):
        bot = BotUserFactory()
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.TIMED)
        MatchFactory(status=Match.Status.FINISHED)

        available = get_available_matches_for_bot(bot)
        pks = set(available.values_list("pk", flat=True))
        assert m1.pk in pks
        assert m2.pk in pks

    def test_excludes_already_bet_matches(self):
        bot = BotUserFactory()
        match = MatchFactory(status=Match.Status.SCHEDULED)
        BetSlipFactory(user=bot, match=match)

        available = get_available_matches_for_bot(bot)
        assert match.pk not in set(available.values_list("pk", flat=True))

    def test_excludes_parlay_matches(self):
        bot = BotUserFactory()
        match = MatchFactory(status=Match.Status.SCHEDULED)
        parlay = ParlayFactory(user=bot)
        ParlayLegFactory(parlay=parlay, match=match)

        available = get_available_matches_for_bot(bot)
        assert match.pk not in set(available.values_list("pk", flat=True))

    def test_returns_empty_when_no_matches(self):
        bot = BotUserFactory()
        available = get_available_matches_for_bot(bot)
        assert not available.exists()


# ---------------------------------------------------------------------------
# get_best_odds_map
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetBestOddsMap:
    def test_returns_min_odds_per_match(self):
        match = MatchFactory()
        OddsFactory(
            match=match,
            bookmaker="BookA",
            home_win=Decimal("2.10"),
            draw=Decimal("3.50"),
            away_win=Decimal("3.80"),
        )
        OddsFactory(
            match=match,
            bookmaker="BookB",
            home_win=Decimal("1.90"),
            draw=Decimal("3.40"),
            away_win=Decimal("4.00"),
        )

        result = get_best_odds_map([match.pk])
        assert result[match.pk]["home_win"] == Decimal("1.90")
        assert result[match.pk]["draw"] == Decimal("3.40")
        assert result[match.pk]["away_win"] == Decimal("3.80")

    def test_returns_empty_for_no_odds(self):
        match = MatchFactory()
        result = get_best_odds_map([match.pk])
        assert result == {}

    def test_handles_multiple_matches(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("1.50"))
        OddsFactory(match=m2, home_win=Decimal("2.50"))

        result = get_best_odds_map([m1.pk, m2.pk])
        assert m1.pk in result
        assert m2.pk in result


# ---------------------------------------------------------------------------
# get_full_odds_map
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetFullOddsMap:
    def test_returns_per_bookmaker_rows(self):
        match = MatchFactory()
        OddsFactory(match=match, bookmaker="BookA", home_win=Decimal("2.00"))
        OddsFactory(match=match, bookmaker="BookB", home_win=Decimal("2.30"))

        result = get_full_odds_map([match.pk])
        assert len(result[match.pk]) == 2

    def test_returns_empty_for_no_odds(self):
        match = MatchFactory()
        result = get_full_odds_map([match.pk])
        assert result == {}


# ---------------------------------------------------------------------------
# place_bot_bet
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPlaceBotBet:
    def test_successful_bet_placement(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, home_win=Decimal("1.80"))

        bet = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("50.00"))
        assert bet is not None
        assert bet.selection == "HOME_WIN"
        assert bet.stake == Decimal("50.00")
        assert bet.odds_at_placement == Decimal("1.80")

        # Balance should be deducted
        balance = UserBalance.objects.get(user=bot)
        assert balance.balance == Decimal("950.00")

    def test_insufficient_balance_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("10.00"))
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, home_win=Decimal("1.80"))

        bet = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("50.00"))
        assert bet is None

    def test_invalid_selection_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        bet = place_bot_bet(bot, match.pk, "INVALID", Decimal("50.00"))
        assert bet is None

    def test_finished_match_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=match)

        bet = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("50.00"))
        assert bet is None

    def test_no_odds_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.SCHEDULED)

        bet = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("50.00"))
        assert bet is None

    def test_no_balance_record_returns_none(self):
        bot = BotUserFactory()
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        bet = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("50.00"))
        assert bet is None

    def test_nonexistent_match_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))

        bet = place_bot_bet(bot, 999999, "HOME_WIN", Decimal("50.00"))
        assert bet is None


# ---------------------------------------------------------------------------
# place_bot_parlay
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPlaceBotParlay:
    def test_successful_parlay_placement(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1, home_win=Decimal("1.80"))
        OddsFactory(match=m2, away_win=Decimal("2.50"))

        legs = [
            {"match_id": m1.pk, "selection": "HOME_WIN"},
            {"match_id": m2.pk, "selection": "AWAY_WIN"},
        ]
        parlay = place_bot_parlay(bot, legs, Decimal("30.00"))
        assert parlay is not None
        assert parlay.stake == Decimal("30.00")
        assert ParlayLeg.objects.filter(parlay=parlay).count() == 2

        balance = UserBalance.objects.get(user=bot)
        assert balance.balance == Decimal("970.00")

    def test_too_few_legs_returns_none(self):
        bot = BotUserFactory()
        legs = [{"match_id": 1, "selection": "HOME_WIN"}]
        result = place_bot_parlay(bot, legs, Decimal("30.00"))
        assert result is None

    def test_too_many_legs_returns_none(self):
        bot = BotUserFactory()
        legs = [{"match_id": i, "selection": "HOME_WIN"} for i in range(11)]
        result = place_bot_parlay(bot, legs, Decimal("30.00"))
        assert result is None

    def test_insufficient_balance_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("10.00"))
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        legs = [
            {"match_id": m1.pk, "selection": "HOME_WIN"},
            {"match_id": m2.pk, "selection": "AWAY_WIN"},
        ]
        result = place_bot_parlay(bot, legs, Decimal("50.00"))
        assert result is None

    def test_finished_match_in_leg_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        legs = [
            {"match_id": m1.pk, "selection": "HOME_WIN"},
            {"match_id": m2.pk, "selection": "AWAY_WIN"},
        ]
        result = place_bot_parlay(bot, legs, Decimal("30.00"))
        assert result is None

    def test_invalid_selection_in_leg_returns_none(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        legs = [
            {"match_id": m1.pk, "selection": "HOME_WIN"},
            {"match_id": m2.pk, "selection": "INVALID"},
        ]
        result = place_bot_parlay(bot, legs, Decimal("30.00"))
        assert result is None

    def test_combined_odds_calculated_correctly(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("1000.00"))
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, away_win=Decimal("3.00"))

        legs = [
            {"match_id": m1.pk, "selection": "HOME_WIN"},
            {"match_id": m2.pk, "selection": "AWAY_WIN"},
        ]
        parlay = place_bot_parlay(bot, legs, Decimal("30.00"))
        assert parlay is not None
        assert parlay.combined_odds == Decimal("6.00")


# ---------------------------------------------------------------------------
# maybe_topup_bot
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMaybeTopupBot:
    def test_no_topup_when_balance_sufficient(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("50000.00"))

        maybe_topup_bot(bot)
        balance = UserBalance.objects.get(user=bot)
        assert balance.balance == Decimal("50000.00")

    def test_topup_when_balance_low_and_no_pending(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("10.00"))

        maybe_topup_bot(bot)
        balance = UserBalance.objects.get(user=bot)
        assert balance.balance > Decimal("10.00")
        assert Bankruptcy.objects.filter(user=bot).exists()
        assert Bailout.objects.filter(user=bot).exists()

    def test_no_topup_when_pending_bets_exist(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("10.00"))
        match = MatchFactory()
        BetSlipFactory(user=bot, match=match)  # status defaults to PENDING

        maybe_topup_bot(bot)
        balance = UserBalance.objects.get(user=bot)
        assert balance.balance == Decimal("10.00")

    def test_no_topup_when_no_balance_record(self):
        bot = BotUserFactory()
        # No UserBalance created — should not raise
        maybe_topup_bot(bot)

    def test_custom_min_balance_threshold(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("80.00"))

        maybe_topup_bot(bot, min_balance=Decimal("100.00"))
        balance = UserBalance.objects.get(user=bot)
        assert balance.balance > Decimal("80.00")

    def test_no_topup_when_pending_parlays_exist(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance=Decimal("10.00"))
        ParlayFactory(user=bot)  # defaults to PENDING

        maybe_topup_bot(bot)
        balance = UserBalance.objects.get(user=bot)
        assert balance.balance == Decimal("10.00")
