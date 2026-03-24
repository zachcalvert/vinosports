from datetime import timedelta

from betting.forms import PlaceBetForm
from betting.models import BetSlip
from discussions.forms import CommentForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from games.models import Conference, Game, GameStatus, Odds, Standing
from vinosports.betting.models import BetStatus


class ScheduleView(LoginRequiredMixin, View):
    def get(self, request):
        date_str = request.GET.get("date")
        conference = request.GET.get("conference")

        if date_str:
            from datetime import date as date_type

            try:
                target_date = date_type.fromisoformat(date_str)
            except ValueError:
                target_date = timezone.localdate()
        else:
            target_date = timezone.localdate()

        games = (
            Game.objects.filter(game_date=target_date)
            .select_related("home_team", "away_team")
            .annotate(
                bet_count=Count("bets", distinct=True),
                comment_count=Count("comments", distinct=True),
            )
            .order_by("tip_off")
        )

        if conference and conference in ("EAST", "WEST"):
            games = games.filter(home_team__conference=conference) | games.filter(
                away_team__conference=conference
            )

        # Build standings lookup for records & seeds
        team_ids = set()
        for g in games:
            team_ids.add(g.home_team_id)
            team_ids.add(g.away_team_id)
        standings_qs = Standing.objects.filter(
            team_id__in=team_ids, season=target_date.year
        ).select_related("team")
        standings_by_team = {s.team_id: s for s in standings_qs}

        prev_date = target_date - timedelta(days=1)
        next_date = target_date + timedelta(days=1)

        ctx = {
            "games": games,
            "target_date": target_date,
            "prev_date": prev_date,
            "next_date": next_date,
            "conference": conference,
            "standings_by_team": standings_by_team,
        }

        if getattr(request, "htmx", False):
            return render(request, "games/partials/schedule_content.html", ctx)
        return render(request, "games/schedule.html", ctx)


class StandingsView(LoginRequiredMixin, View):
    def get(self, request):
        from games.tasks import _current_season

        season = _current_season()
        east = (
            Standing.objects.filter(season=season, conference=Conference.EAST)
            .select_related("team")
            .order_by("conference_rank")
        )

        west = (
            Standing.objects.filter(season=season, conference=Conference.WEST)
            .select_related("team")
            .order_by("conference_rank")
        )

        tab = request.GET.get("tab", "west")

        ctx = {
            "east_standings": east,
            "west_standings": west,
            "tab": tab,
            "season": season,
        }

        if getattr(request, "htmx", False):
            return render(request, "games/partials/standings_table.html", ctx)
        return render(request, "games/standings.html", ctx)


def _get_game_sentiment(game):
    """Aggregate moneyline bet sentiment for a game (Home vs Away, no draw in NBA)."""
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
    away_pct = 100 - home_pct  # avoids rounding drift

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

    if game.home_score > game.away_score:
        actual_result = "HOME"
        actual_result_label = "Home"
        winner_name = home_name
        loser_name = away_name
    else:
        actual_result = "AWAY"
        actual_result_label = "Away"
        winner_name = away_name
        loser_name = home_name

    # Check for upset based on standings
    standings = Standing.objects.filter(
        team__in=[game.home_team, game.away_team],
        season=game.season,
    ).select_related("team")
    standing_map = {s.team_id: s for s in standings}
    home_standing = standing_map.get(game.home_team_id)
    away_standing = standing_map.get(game.away_team_id)

    is_upset = False
    if home_standing and away_standing:
        winner_standing = home_standing if actual_result == "HOME" else away_standing
        loser_standing = away_standing if actual_result == "HOME" else home_standing
        if winner_standing.conference_rank and loser_standing.conference_rank:
            is_upset = winner_standing.conference_rank > loser_standing.conference_rank

    if is_upset:
        headline = (
            f"{winner_name} pull off the upset against {loser_name} ({score_line})"
        )
    else:
        headline = f"{winner_name} beat {loser_name} ({score_line})"

    result_context = {
        "headline": headline,
        "is_upset": is_upset,
        "score_line": score_line,
    }

    # Betting outcome aggregates (all markets, not just moneyline)
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

        from discussions.models import Comment

        comments = (
            Comment.objects.filter(game=game, parent__isnull=True)
            .select_related("user")
            .prefetch_related("replies__user")
            .order_by("-created_at")[:50]
        )

        # Community sentiment per market
        sentiment = _get_game_sentiment(game)
        spread_sentiment = _get_spread_sentiment(game)
        total_sentiment = _get_total_sentiment(game)

        # Recap context for finished games
        recap_ctx = {}
        if game.status == GameStatus.FINAL:
            recap_ctx = _get_recap_context(game)

        ctx = {
            "game": game,
            "odds_list": odds[:5],
            "best_odds": best_odds,
            "comments": comments,
            "bet_form": PlaceBetForm(),
            "comment_form": CommentForm(),
            "sentiment": sentiment,
            "spread_sentiment": spread_sentiment,
            "total_sentiment": total_sentiment,
        }
        ctx.update(recap_ctx)

        return render(request, "games/game_detail.html", ctx)
