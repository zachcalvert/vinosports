from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from nba.betting.forms import PlaceBetForm
from nba.betting.models import BetSlip
from nba.discussions.forms import CommentForm
from nba.games.models import (
    Conference,
    Game,
    GameStatus,
    Odds,
    Player,
    PlayerBoxScore,
    Standing,
    Team,
)
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
            .order_by("tip_off")
        )

        if conference and conference in ("EAST", "WEST"):
            games = games.filter(home_team__conference=conference) | games.filter(
                away_team__conference=conference
            )

        # Build standings lookup for records & seeds
        team_ids = set()
        games_list = list(games)
        for g in games_list:
            team_ids.add(g.home_team_id)
            team_ids.add(g.away_team_id)
        standings_qs = Standing.objects.filter(
            team_id__in=team_ids, season=target_date.year
        ).select_related("team")
        standings_by_team = {s.team_id: s for s in standings_qs}

        # Build odds lookup (most recent per game)
        odds_by_game = {}
        for g in games_list:
            first_odds = g.odds.all()[:1]
            if first_odds:
                odds_by_game[g.id] = first_odds[0]

        # Pick featured game: most bets among non-final games, fallback to first
        featured_game = None
        remaining_games = games_list
        non_final = [g for g in games_list if not g.is_final]
        if non_final:
            featured_game = max(non_final, key=lambda g: g.bet_count)
            remaining_games = [g for g in games_list if g.id != featured_game.id]
        elif games_list:
            featured_game = games_list[0]
            remaining_games = games_list[1:]

        # Build week date strip (3 days before + target + 3 days after)
        week_dates = []
        for offset in range(-3, 4):
            d = target_date + timedelta(days=offset)
            week_dates.append(
                {
                    "date": d,
                    "is_selected": d == target_date,
                }
            )

        ctx = {
            "games": remaining_games,
            "featured_game": featured_game,
            "target_date": target_date,
            "week_dates": week_dates,
            "conference": conference,
            "standings_by_team": standings_by_team,
            "odds_by_game": odds_by_game,
        }

        htmx = getattr(request, "htmx", False)
        if htmx and not htmx.boosted:
            return render(request, "games/partials/schedule_content.html", ctx)
        return render(request, "games/schedule.html", ctx)


class StandingsView(LoginRequiredMixin, View):
    def get(self, request):
        from nba.games.tasks import _current_season

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
        active_standings = east if tab == "east" else west

        # Projected first-round matchup: seed 1 vs seed 8
        projected_matchup = {}
        if active_standings.count() >= 8:
            projected_matchup = {
                "seed_1": active_standings[0],
                "seed_8": active_standings[7],
            }

        # Division leaders: top 3 teams in the #1 seed's division
        division_name = ""
        division_leaders = Standing.objects.none()
        if active_standings.exists():
            division_name = active_standings[0].team.division
            division_leaders = (
                Standing.objects.filter(season=season, team__division=division_name)
                .select_related("team")
                .order_by("conference_rank")[:3]
            )

        ctx = {
            "east_standings": east,
            "west_standings": west,
            "tab": tab,
            "season": season,
            "projected_matchup": projected_matchup,
            "division_leaders": division_leaders,
            "division_name": division_name,
        }

        htmx = getattr(request, "htmx", False)
        if htmx and not htmx.boosted:
            return render(request, "games/partials/standings_panel.html", ctx)
        return render(request, "games/standings.html", ctx)


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
        return render(request, "games/player_list.html", ctx)


class PlayerDetailView(LoginRequiredMixin, View):
    def get(self, request, slug):
        id_hash = slug.rsplit("-", 1)[-1]
        player = get_object_or_404(
            Player.objects.select_related("team"),
            id_hash=id_hash,
        )
        if slug != player.slug:
            return redirect(player.get_absolute_url(), permanent=True)

        # Recent box scores (last 10 games)
        recent_box_scores = player.box_scores.select_related(
            "game__home_team", "game__away_team"
        ).order_by("-game__game_date")[:10]

        # Season averages (current season, regular season only)
        from django.db.models import Avg, Count

        from nba.games.tasks import _current_season

        season = _current_season()
        season_games = player.box_scores.filter(
            game__season=season,
            game__postseason=False,
            game__status=GameStatus.FINAL,
        )
        averages = season_games.aggregate(
            games_played=Count("id"),
            ppg=Avg("points"),
            rpg=Avg("reb"),
            apg=Avg("ast"),
            spg=Avg("stl"),
            bpg=Avg("blk"),
            topg=Avg("turnovers"),
            fgm_avg=Avg("fgm"),
            fga_avg=Avg("fga"),
            fg3m_avg=Avg("fg3m"),
            fg3a_avg=Avg("fg3a"),
            ftm_avg=Avg("ftm"),
            fta_avg=Avg("fta"),
        )

        ctx = {
            "player": player,
            "recent_box_scores": recent_box_scores,
            "averages": averages,
            "season": season,
        }
        return render(request, "games/player_detail.html", ctx)


class TeamDetailView(LoginRequiredMixin, View):
    def get(self, request, abbreviation):
        from nba.games.tasks import _current_season

        team = get_object_or_404(Team, abbreviation__iexact=abbreviation)
        season = _current_season()
        today = timezone.localdate()

        standing = Standing.objects.filter(team=team, season=season).first()

        roster = Player.objects.filter(team=team, is_active=True).order_by(
            "last_name", "first_name"
        )

        last_game = (
            Game.objects.filter(
                Q(home_team=team) | Q(away_team=team), status=GameStatus.FINAL
            )
            .select_related("home_team", "away_team")
            .order_by("-game_date", "-tip_off")
            .first()
        )

        next_game = (
            Game.objects.filter(
                Q(home_team=team) | Q(away_team=team),
                status=GameStatus.SCHEDULED,
                game_date__gte=today,
            )
            .select_related("home_team", "away_team")
            .order_by("game_date", "tip_off")
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
        return render(request, "games/team_detail.html", ctx)


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


def _get_box_score_context(game):
    """Build box score data grouped by team for template rendering."""
    if game.status not in (
        GameStatus.IN_PROGRESS,
        GameStatus.HALFTIME,
        GameStatus.FINAL,
    ):
        return {}

    box_scores = PlayerBoxScore.objects.filter(game=game).select_related(
        "team", "player"
    )

    # On-demand fetch if no data exists yet
    if not box_scores.exists():
        from nba.games.services import sync_box_score

        try:
            sync_box_score(game)
            box_scores = PlayerBoxScore.objects.filter(game=game).select_related(
                "team", "player"
            )
        except Exception:
            return {}

    if not box_scores.exists():
        return {}

    away_all = list(box_scores.filter(team=game.away_team))
    home_all = list(box_scores.filter(team=game.home_team))
    away_starters = [p for p in away_all if p.starter]
    away_bench = [p for p in away_all if not p.starter]
    home_starters = [p for p in home_all if p.starter]
    home_bench = [p for p in home_all if not p.starter]

    def _team_totals(players):
        totals = {
            "points": 0,
            "reb": 0,
            "ast": 0,
            "stl": 0,
            "blk": 0,
            "turnovers": 0,
            "pf": 0,
            "fgm": 0,
            "fga": 0,
            "fg3m": 0,
            "fg3a": 0,
            "ftm": 0,
            "fta": 0,
        }
        for p in players:
            for key in totals:
                totals[key] += getattr(p, key)
        return totals

    return {
        "away_starters": away_starters,
        "away_bench": away_bench,
        "home_starters": home_starters,
        "home_bench": home_bench,
        "away_totals": _team_totals(away_all),
        "home_totals": _team_totals(home_all),
        "has_box_score": True,
    }


class GameDetailView(LoginRequiredMixin, View):
    def get(self, request, id_hash):
        game = get_object_or_404(
            Game.objects.select_related("home_team", "away_team"),
            id_hash=id_hash,
        )

        odds = Odds.objects.filter(game=game).order_by("-fetched_at")
        best_odds = odds.first()

        from django.db.models import Prefetch

        from nba.discussions.models import Comment

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
        if game.status == GameStatus.FINAL:
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
        }
        ctx.update(recap_ctx)
        ctx.update(_get_box_score_context(game))

        return render(request, "games/game_detail.html", ctx)
