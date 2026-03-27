"""Tests for NBA model validation, constraints, and properties."""

from decimal import Decimal

import pytest
from django.db import IntegrityError

from nba.games.models import GameStatus
from nba.tests.factories import (
    BetSlipFactory,
    BotProfileFactory,
    BotUserFactory,
    CommentFactory,
    GameFactory,
    OddsFactory,
    ParlayFactory,
    ParlayLegFactory,
    PlayerFactory,
    StandingFactory,
    TeamFactory,
)
from vinosports.betting.models import BetStatus

# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTeam:
    def test_str(self):
        team = TeamFactory(short_name="Boston Celtics")
        assert str(team) == "Boston Celtics"

    def test_ordering(self):
        TeamFactory(short_name="Zebras")
        TeamFactory(short_name="Alphas")
        from nba.games.models import Team

        names = list(Team.objects.values_list("short_name", flat=True))
        assert names.index("Alphas") < names.index("Zebras")


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPlayer:
    def test_str(self):
        player = PlayerFactory(first_name="LeBron", last_name="James")
        assert str(player) == "LeBron James"

    def test_full_name_property(self):
        player = PlayerFactory(first_name="Stephen", last_name="Curry")
        assert player.full_name == "Stephen Curry"

    def test_slug_property(self):
        player = PlayerFactory(first_name="LeBron", last_name="James")
        assert player.slug == f"lebron-james-{player.id_hash}"

    def test_get_absolute_url(self):
        player = PlayerFactory(first_name="Stephen", last_name="Curry")
        url = player.get_absolute_url()
        assert url == f"/nba/games/players/stephen-curry-{player.id_hash}/"

    def test_unique_external_id(self):
        PlayerFactory(external_id=99999)
        with pytest.raises(IntegrityError):
            PlayerFactory(external_id=99999)

    def test_team_fk_nullable(self):
        player = PlayerFactory(team=None)
        assert player.team is None
        assert player.pk is not None


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGame:
    def test_str(self):
        home = TeamFactory(abbreviation="BOS")
        away = TeamFactory(abbreviation="LAL")
        game = GameFactory(home_team=home, away_team=away)
        assert "LAL @ BOS" in str(game)

    def test_is_live_in_progress(self):
        game = GameFactory(status=GameStatus.IN_PROGRESS)
        assert game.is_live is True

    def test_is_live_halftime(self):
        game = GameFactory(status=GameStatus.HALFTIME)
        assert game.is_live is True

    def test_is_live_false_for_scheduled(self):
        game = GameFactory(status=GameStatus.SCHEDULED)
        assert game.is_live is False

    def test_is_final(self):
        game = GameFactory(status=GameStatus.FINAL)
        assert game.is_final is True

    def test_is_final_false(self):
        game = GameFactory(status=GameStatus.SCHEDULED)
        assert game.is_final is False

    def test_winner_home_wins(self):
        game = GameFactory(status=GameStatus.FINAL, home_score=110, away_score=95)
        assert game.winner == game.home_team

    def test_winner_away_wins(self):
        game = GameFactory(status=GameStatus.FINAL, home_score=90, away_score=105)
        assert game.winner == game.away_team

    def test_winner_not_final(self):
        game = GameFactory(status=GameStatus.SCHEDULED)
        assert game.winner is None

    def test_winner_no_scores(self):
        game = GameFactory(status=GameStatus.FINAL, home_score=None, away_score=None)
        assert game.winner is None

    def test_get_absolute_url(self):
        game = GameFactory()
        url = game.get_absolute_url()
        assert url == f"/nba/games/{game.id_hash}/"


# ---------------------------------------------------------------------------
# Standing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStanding:
    def test_str(self):
        team = TeamFactory(abbreviation="BOS")
        standing = StandingFactory(team=team, season=2026, wins=50, losses=12)
        assert "BOS 2026 (50-12)" == str(standing)

    def test_unique_together(self):
        team = TeamFactory()
        StandingFactory(team=team, season=2026)
        with pytest.raises(IntegrityError):
            StandingFactory(team=team, season=2026)


# ---------------------------------------------------------------------------
# BetSlip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBetSlip:
    def test_str(self):
        bet = BetSlipFactory(odds_at_placement=-150)
        assert "-150" in str(bet)

    def test_calculate_payout_negative_odds(self):
        bet = BetSlipFactory(stake=Decimal("100.00"), odds_at_placement=-150)
        payout = bet.calculate_payout()
        # -150: win 100/150*100 = 66.67 + 100 = 166.67
        assert payout == pytest.approx(Decimal("166.67"), abs=Decimal("0.01"))

    def test_calculate_payout_positive_odds(self):
        bet = BetSlipFactory(stake=Decimal("100.00"), odds_at_placement=200)
        payout = bet.calculate_payout()
        # +200: win 200/100*100 = 200 + 100 = 300
        assert payout == Decimal("300.00")

    def test_default_status_pending(self):
        bet = BetSlipFactory()
        assert bet.status == BetStatus.PENDING


# ---------------------------------------------------------------------------
# Parlay
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestParlay:
    def test_str(self):
        parlay = ParlayFactory(combined_odds=600)
        assert "600" in str(parlay)

    def test_default_status_pending(self):
        parlay = ParlayFactory()
        assert parlay.status == BetStatus.PENDING


# ---------------------------------------------------------------------------
# ParlayLeg unique constraint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestParlayLeg:
    def test_unique_together_parlay_game(self):
        game = GameFactory()
        parlay = ParlayFactory()
        ParlayLegFactory(parlay=parlay, game=game)
        with pytest.raises(IntegrityError):
            ParlayLegFactory(parlay=parlay, game=game)


# ---------------------------------------------------------------------------
# BotComment unique constraint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBotComment:
    def test_unique_constraint_per_trigger(self):
        from nba.bots.models import BotComment

        bot_user = BotUserFactory()
        BotProfileFactory(user=bot_user)
        game = GameFactory()

        BotComment.objects.create(user=bot_user, game=game, trigger_type="PRE_MATCH")
        with pytest.raises(IntegrityError):
            BotComment.objects.create(
                user=bot_user, game=game, trigger_type="PRE_MATCH"
            )


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestComment:
    def test_str(self):
        comment = CommentFactory()
        assert comment.user.email in str(comment)

    def test_reply_parent(self):
        parent = CommentFactory()
        reply = CommentFactory(game=parent.game, parent=parent)
        assert reply.parent == parent


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOdds:
    def test_str(self):
        odds = OddsFactory(bookmaker="House")
        assert "House" in str(odds)

    def test_unique_together_game_bookmaker(self):
        game = GameFactory()
        OddsFactory(game=game, bookmaker="House")
        with pytest.raises(IntegrityError):
            OddsFactory(game=game, bookmaker="House")


@pytest.mark.django_db
class TestActivityEventStr:
    def test_str_shows_sent_status_when_broadcast(self):
        from django.utils import timezone
        from nba.activity.models import ActivityEvent
        event = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="LAL 110 - BOS 105",
            broadcast_at=timezone.now(),
        )
        assert str(event) == "[sent] LAL 110 - BOS 105"

    def test_str_shows_queued_status_when_not_broadcast(self):
        from nba.activity.models import ActivityEvent
        event = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.BOT_BET,
            message="Bot placed a bet",
        )
        assert str(event) == "[queued] Bot placed a bet"
