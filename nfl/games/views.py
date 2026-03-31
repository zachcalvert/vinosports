from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from nfl.betting.forms import PlaceBetForm
from nfl.betting.models import BetSlip, Odds
from nfl.discussions.forms import CommentForm
from nfl.games.models import (
    Conference,
    Game,
    GameStatus,
    Player,
    Standing,
    Team,
)
from vinosports.betting.models import BetStatus


def _nfl_current_season():
    """NFL season starts in September."""
    today = timezone.localdate()
    return today.year if today.month >= 9 else today.year - 1


def _nfl_current_week(season):
    """Determine the most relevant week for the current season."""
    today = timezone.localdate()
    # Find the latest week with games on or before today
    week = (
        Game.objects.filter(season=season, game_date__lte=today)
        .order_by("-week")
        .values_list("week", flat=True)
        .first()
    )
    if week:
        return week
    # No games yet — return week 1
    return 1


class ScheduleView(LoginRequiredMixin, View):
    """Week-based schedule for NFL (not date-based like NBA)."""

    def get(self, request):
        season = _nfl_current_season()
        week_str = request.GET.get("week")
        conference = request.GET.get("conference")

        if week_str:
            try:
                target_week = int(week_str)
            except ValueError:
                target_week = _nfl_current_week(season)
        else:
            target_week = _nfl_current_week(season)

        games = (
            Game.objects.filter(season=season, week=target_week)
            .select_related("home_team", "away_team")
            .prefetch_related(
                Prefetch(
                    "odds",
                    queryset=Odds.objects.order_by("-fetched_at"),
                )
            )
            .annotate(
                bet_count=Count("bets", distinct=True),
                comment_count=Count("comments", distinct=True),
            )
            .order_by("kickoff", "game_date")
        )

        if conference and conference in ("AFC", "NFC"):
            games = games.filter(
                Q(home_team__conference=conference)
                | Q(away_team__conference=conference)
            )

        # Build standings lookup for records
        games_list = list(games)
        team_ids = set()
        for g in games_list:
            team_ids.add(g.home_team_id)
            team_ids.add(g.away_team_id)
        standings_qs = Standing.objects.filter(
            team_id__in=team_ids, season=season
        ).select_related("team")
        standings_by_team = {s.team_id: s for s in standings_qs}

        # Odds lookup (most recent per game)
        odds_by_game = {}
        for g in games_list:
            first_odds = g.odds.all()[:1]
            if first_odds:
                odds_by_game[g.id] = first_odds[0]

        # Featured game: most bets among non-final games
        featured_game = None
        remaining_games = games_list
        non_final = [g for g in games_list if not g.is_final]
        if non_final:
            featured_game = max(non_final, key=lambda g: g.bet_count)
            remaining_games = [g for g in games_list if g.id != featured_game.id]
        elif games_list:
            featured_game = games_list[0]
            remaining_games = games_list[1:]

        # Build week navigation strip
        max_week = (
            Game.objects.filter(season=season)
            .order_by("-week")
            .values_list("week", flat=True)
            .first()
        ) or 18
        weeks = []
        for w in range(1, max_week + 1):
            weeks.append({"week": w, "is_selected": w == target_week})

        ctx = {
            "games": remaining_games,
            "featured_game": featured_game,
            "target_week": target_week,
            "weeks": weeks,
            "conference": conference,
            "standings_by_team": standings_by_team,
            "odds_by_game": odds_by_game,
            "season": season,
        }

        htmx = getattr(request, "htmx", False)
        if htmx and not htmx.boosted:
            return render(request, "nfl_games/partials/schedule_content.html", ctx)
        return render(request, "nfl_games/schedule.html", ctx)


class StandingsView(LoginRequiredMixin, View):
    """Division-centric standings for NFL."""

    def get(self, request):
        season = _nfl_current_season()
        tab = request.GET.get("tab", "AFC")

        standings = (
            Standing.objects.filter(season=season)
            .select_related("team")
            .order_by("division", "division_rank")
        )

        # Group by division within each conference
        afc_divisions = {}
        nfc_divisions = {}
        for s in standings:
            if s.conference == Conference.AFC:
                afc_divisions.setdefault(s.division, []).append(s)
            else:
                nfc_divisions.setdefault(s.division, []).append(s)

        # Sort division keys for consistent rendering
        afc_ordered = sorted(afc_divisions.items(), key=lambda x: x[0])
        nfc_ordered = sorted(nfc_divisions.items(), key=lambda x: x[0])

        ctx = {
            "afc_divisions": afc_ordered,
            "nfc_divisions": nfc_ordered,
            "tab": tab,
            "season": season,
        }

        htmx = getattr(request, "htmx", False)
        if htmx and not htmx.boosted:
            return render(request, "nfl_games/partials/standings_panel.html", ctx)
        return render(request, "nfl_games/standings.html", ctx)


class PlayerListView(LoginRequiredMixin, View):
    def get(self, request):
        team_abbr = request.GET.get("team")
        position = request.GET.get("position")

        players = (
            Player.objects.select_related("team")
            .filter(is_active=True)
            .order_by("team__short_name", "last_name")
        )

        if team_abbr:
            players = players.filter(team__abbreviation=team_abbr)
        if position:
            players = players.filter(position__icontains=position)

        teams = Team.objects.order_by("short_name")

        ctx = {
            "players": players,
            "teams": teams,
            "selected_team": team_abbr,
            "selected_position": position,
        }
        return render(request, "nfl_games/player_list.html", ctx)


class PlayerDetailView(LoginRequiredMixin, View):
    def get(self, request, slug):
        id_hash = slug.rsplit("-", 1)[-1]
        player = get_object_or_404(
            Player.objects.select_related("team"),
            id_hash=id_hash,
        )
        if slug != player.slug:
            return redirect(player.get_absolute_url(), permanent=True)

        ctx = {
            "player": player,
            "season": _nfl_current_season(),
        }
        return render(request, "nfl_games/player_detail.html", ctx)


class TeamDetailView(LoginRequiredMixin, View):
    def get(self, request, abbreviation):
        season = _nfl_current_season()
        today = timezone.localdate()

        team = get_object_or_404(Team, abbreviation__iexact=abbreviation)
        standing = Standing.objects.filter(team=team, season=season).first()

        roster = Player.objects.filter(team=team, is_active=True).order_by(
            "last_name", "first_name"
        )

        last_game = (
            Game.objects.filter(
                Q(home_team=team) | Q(away_team=team),
                status__in=[GameStatus.FINAL, GameStatus.FINAL_OT],
            )
            .select_related("home_team", "away_team")
            .order_by("-game_date", "-kickoff")
            .first()
        )

        next_game = (
            Game.objects.filter(
                Q(home_team=team) | Q(away_team=team),
                status=GameStatus.SCHEDULED,
                game_date__gte=today,
            )
            .select_related("home_team", "away_team")
            .order_by("game_date", "kickoff")
            .first()
        )

        # Opponent standings for game cards
        opponent_ids = set()
        if last_game:
            opp = (
                last_game.away_team
                if last_game.home_team == team
                else last_game.home_team
            )
            opponent_ids.add(opp.id)
        if next_game:
            opp = (
                next_game.away_team
                if next_game.home_team == team
                else next_game.home_team
            )
            opponent_ids.add(opp.id)
        standings_by_team = {}
        if opponent_ids:
            for s in Standing.objects.filter(team_id__in=opponent_ids, season=season):
                standings_by_team[s.team_id] = s

        ctx = {
            "team": team,
            "standing": standing,
            "roster": roster,
            "last_game": last_game,
            "next_game": next_game,
            "standings_by_team": standings_by_team,
            "season": season,
        }
        return render(request, "nfl_games/team_detail.html", ctx)


# ---------------------------------------------------------------------------
# Sentiment helpers
# ---------------------------------------------------------------------------


def _get_game_sentiment(game):
    """Aggregate moneyline bet sentiment for a game (Home vs Away)."""
    rows = (
        BetSlip.objects.filter(game=game, market=BetSlip.Market.MONEYLINE)
        .values("selection")
        .annotate(count=Count("id"))
    )
    counts = {r["selection"]: r["count"] for r in rows}
    total = sum(counts.values())

    if not total:
        return None

    home_pct = round(counts.get(BetSlip.Selection.HOME, 0) / total * 100)
    away_pct = 100 - home_pct

    most_popular_sel = (
        BetSlip.Selection.HOME if home_pct >= away_pct else BetSlip.Selection.AWAY
    )
    most_popular_label = dict(BetSlip.Selection.choices)[most_popular_sel]

    return {
        "total": total,
        "home_pct": home_pct,
        "away_pct": away_pct,
        "most_popular": most_popular_label,
    }


def _get_spread_sentiment(game):
    """Aggregate spread bet sentiment (Home vs Away)."""
    rows = (
        BetSlip.objects.filter(game=game, market=BetSlip.Market.SPREAD)
        .values("selection")
        .annotate(count=Count("id"))
    )
    counts = {r["selection"]: r["count"] for r in rows}
    total = sum(counts.values())

    if not total:
        return None

    home_pct = round(counts.get(BetSlip.Selection.HOME, 0) / total * 100)
    away_pct = 100 - home_pct

    return {
        "total": total,
        "home_pct": home_pct,
        "away_pct": away_pct,
    }


def _get_total_sentiment(game):
    """Aggregate total bet sentiment (Over vs Under)."""
    rows = (
        BetSlip.objects.filter(game=game, market=BetSlip.Market.TOTAL)
        .values("selection")
        .annotate(count=Count("id"))
    )
    counts = {r["selection"]: r["count"] for r in rows}
    total = sum(counts.values())

    if not total:
        return None

    over_pct = round(counts.get(BetSlip.Selection.OVER, 0) / total * 100)
    under_pct = 100 - over_pct

    return {
        "total": total,
        "over_pct": over_pct,
        "under_pct": under_pct,
    }


def _get_recap_context(game):
    """Build result headline and betting outcome data for finished games."""
    if game.home_score is None or game.away_score is None:
        return {}

    home_name = game.home_team.short_name
    away_name = game.away_team.short_name
    score_line = f"{game.away_score}-{game.home_score}"

    # NFL has ties
    if game.is_tie:
        headline = f"{away_name} and {home_name} tie ({score_line})"
        actual_result = "TIE"
        actual_result_label = "Tie"
    elif game.home_score > game.away_score:
        actual_result = "HOME"
        actual_result_label = "Home"
        winner_name = home_name
        loser_name = away_name
        headline = f"{winner_name} beat {loser_name} ({score_line})"
    else:
        actual_result = "AWAY"
        actual_result_label = "Away"
        winner_name = away_name
        loser_name = home_name
        headline = f"{winner_name} beat {loser_name} ({score_line})"

    result_context = {
        "headline": headline,
        "score_line": score_line,
    }

    # Betting outcome aggregates
    agg = BetSlip.objects.filter(game=game).aggregate(
        total_bets=Count("id"),
        winners=Count("id", filter=Q(status=BetStatus.WON)),
        total_staked=Sum("stake"),
        total_won_payout=Sum("payout", filter=Q(status=BetStatus.WON)),
    )
    total = agg["total_bets"] or 0
    betting_outcome = None
    if total:
        betting_outcome = {
            "total_bets": total,
            "winners": agg["winners"],
            "win_pct": round(agg["winners"] / total * 100),
            "total_staked": agg["total_staked"],
            "total_won_payout": agg["total_won_payout"] or 0,
        }

    return {
        "result_context": result_context,
        "betting_outcome": betting_outcome,
        "actual_result": actual_result,
        "actual_result_label": actual_result_label,
    }


class GameDetailView(LoginRequiredMixin, View):
    def get(self, request, id_hash):
        game = get_object_or_404(
            Game.objects.select_related("home_team", "away_team"),
            id_hash=id_hash,
        )

        odds = Odds.objects.filter(game=game).order_by("-fetched_at")
        best_odds = odds.first()

        from nfl.discussions.models import Comment

        replies_qs = (
            Comment.objects.filter(is_deleted=False)
            .select_related("user")
            .order_by("created_at")
        )
        comments = (
            Comment.objects.filter(game=game, parent__isnull=True)
            .select_related("user")
            .prefetch_related(
                Prefetch("replies", queryset=replies_qs, to_attr="prefetched_replies")
            )
            .order_by("-created_at")[:50]
        )

        # Community sentiment per market
        sentiment = _get_game_sentiment(game)
        spread_sentiment = _get_spread_sentiment(game)
        total_sentiment = _get_total_sentiment(game)

        # Recap context for finished games
        recap_ctx = {}
        if game.is_final:
            recap_ctx = _get_recap_context(game)

        user_bets = BetSlip.objects.filter(user=request.user, game=game).order_by(
            "-created_at"
        )

        # Team standings (records)
        season = game.season
        standings_qs = Standing.objects.filter(
            team__in=[game.home_team, game.away_team], season=season
        )
        standings_map = {s.team_id: s for s in standings_qs}

        # Quarter-by-quarter scoring
        quarter_scores = None
        if game.status in (
            GameStatus.IN_PROGRESS,
            GameStatus.HALFTIME,
            GameStatus.FINAL,
            GameStatus.FINAL_OT,
        ):
            quarter_scores = {
                "home": [game.home_q1, game.home_q2, game.home_q3, game.home_q4],
                "away": [game.away_q1, game.away_q2, game.away_q3, game.away_q4],
                "has_ot": game.home_ot is not None or game.away_ot is not None,
                "home_ot": game.home_ot,
                "away_ot": game.away_ot,
            }

        ctx = {
            "game": game,
            "odds_list": odds[:5],
            "best_odds": best_odds,
            "comments": comments,
            "bet_form": PlaceBetForm(),
            "comment_form": CommentForm(),
            "user_bets": user_bets,
            "sentiment": sentiment,
            "spread_sentiment": spread_sentiment,
            "total_sentiment": total_sentiment,
            "home_standing": standings_map.get(game.home_team_id),
            "away_standing": standings_map.get(game.away_team_id),
            "quarter_scores": quarter_scores,
        }
        ctx.update(recap_ctx)

        return render(request, "nfl_games/game_detail.html", ctx)
