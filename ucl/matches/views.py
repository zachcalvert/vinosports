from django.views.generic import DetailView, ListView, TemplateView

from ucl.matches.models import Match, Stage, Standing


class DashboardView(TemplateView):
    template_name = "ucl_matches/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["upcoming_matches"] = Match.objects.filter(
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED]
        ).select_related("home_team", "away_team", "stage")[:10]
        ctx["live_matches"] = Match.objects.filter(
            status__in=[
                Match.Status.IN_PLAY,
                Match.Status.PAUSED,
                Match.Status.EXTRA_TIME,
                Match.Status.PENALTY_SHOOTOUT,
            ]
        ).select_related("home_team", "away_team", "stage")
        ctx["recent_results"] = (
            Match.objects.filter(status=Match.Status.FINISHED)
            .select_related("home_team", "away_team", "stage")
            .order_by("-kickoff")[:10]
        )
        ctx["stages"] = Stage.objects.all()
        return ctx


class StandingsView(ListView):
    """League phase standings — single 36-team table."""

    model = Standing
    template_name = "ucl_matches/standings.html"
    context_object_name = "standings"

    def get_queryset(self):
        return Standing.objects.select_related("team").order_by("position")


class BracketView(TemplateView):
    template_name = "ucl_matches/bracket.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        knockout_stages = Stage.objects.exclude(
            stage_type=Stage.StageType.LEAGUE_PHASE
        ).order_by("order")
        ctx["stages"] = knockout_stages
        ctx["knockout_matches"] = {}
        for stage in knockout_stages:
            ctx["knockout_matches"][stage.stage_type] = (
                Match.objects.filter(stage=stage)
                .select_related("home_team", "away_team")
                .order_by("tie_id", "leg", "kickoff")
            )
        return ctx


class MatchDetailView(DetailView):
    model = Match
    template_name = "ucl_matches/match_detail.html"
    context_object_name = "match"

    def get_queryset(self):
        return Match.objects.select_related("home_team", "away_team", "stage")

    def get_context_data(self, **kwargs):
        from ucl.betting.views import _get_match_sentiment

        ctx = super().get_context_data(**kwargs)
        ctx["odds"] = self.object.odds.first()
        ctx["sentiment"] = _get_match_sentiment(self.object)
        return ctx


class LeaderboardView(TemplateView):
    template_name = "ucl_matches/leaderboard.html"

    def get_context_data(self, **kwargs):
        from vinosports.betting.models import UserStats

        ctx = super().get_context_data(**kwargs)
        ctx["leaderboard"] = UserStats.objects.select_related("user").order_by(
            "-net_profit"
        )[:50]
        return ctx


class LeaderboardPartialView(LeaderboardView):
    template_name = "ucl_matches/partials/leaderboard_body.html"
