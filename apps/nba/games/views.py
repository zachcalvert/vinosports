from datetime import timedelta

from betting.forms import PlaceBetForm
from discussions.forms import CommentForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from games.models import Conference, Game, Odds, Standing


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
            return render(request, "games/partials/game_list.html", ctx)
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

        return render(
            request,
            "games/game_detail.html",
            {
                "game": game,
                "odds_list": odds[:5],
                "best_odds": best_odds,
                "comments": comments,
                "bet_form": PlaceBetForm(),
                "comment_form": CommentForm(),
            },
        )
