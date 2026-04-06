from django.views.generic import DetailView, ListView, TemplateView

from worldcup.matches.models import Group, Match, Stage, Standing


class DashboardView(TemplateView):
    template_name = "worldcup_matches/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["upcoming_matches"] = Match.objects.filter(
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED]
        ).select_related("home_team", "away_team", "stage", "group")[:10]
        ctx["live_matches"] = Match.objects.filter(
            status__in=[
                Match.Status.IN_PLAY,
                Match.Status.PAUSED,
                Match.Status.EXTRA_TIME,
                Match.Status.PENALTY_SHOOTOUT,
            ]
        ).select_related("home_team", "away_team", "stage", "group")
        ctx["recent_results"] = (
            Match.objects.filter(status=Match.Status.FINISHED)
            .select_related("home_team", "away_team", "stage", "group")
            .order_by("-kickoff")[:10]
        )
        ctx["stages"] = Stage.objects.all()
        return ctx


class GroupsView(ListView):
    model = Group
    template_name = "worldcup_matches/groups.html"
    context_object_name = "groups"

    def get_queryset(self):
        return Group.objects.prefetch_related(
            "teams", "standings", "standings__team"
        ).order_by("letter")


class GroupDetailView(DetailView):
    model = Group
    template_name = "worldcup_matches/group_detail.html"
    context_object_name = "group"
    slug_field = "letter"
    slug_url_kwarg = "letter"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["standings"] = Standing.objects.filter(group=self.object).select_related(
            "team"
        )
        ctx["matches"] = (
            Match.objects.filter(group=self.object)
            .select_related("home_team", "away_team", "stage")
            .order_by("kickoff")
        )
        return ctx


class BracketView(TemplateView):
    template_name = "worldcup_matches/bracket.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        knockout_stages = Stage.objects.exclude(
            stage_type=Stage.StageType.GROUP
        ).order_by("order")
        ctx["stages"] = knockout_stages
        ctx["knockout_matches"] = {}
        for stage in knockout_stages:
            ctx["knockout_matches"][stage.stage_type] = (
                Match.objects.filter(stage=stage)
                .select_related("home_team", "away_team")
                .order_by("kickoff")
            )
        return ctx


class MatchDetailView(DetailView):
    model = Match
    template_name = "worldcup_matches/match_detail.html"
    context_object_name = "match"

    def get_queryset(self):
        return Match.objects.select_related("home_team", "away_team", "stage", "group")

    def get_context_data(self, **kwargs):
        from worldcup.betting.views import _get_match_sentiment

        ctx = super().get_context_data(**kwargs)
        ctx["odds"] = self.object.odds.first()
        ctx["sentiment"] = _get_match_sentiment(self.object)
        return ctx


class LeaderboardView(TemplateView):
    template_name = "worldcup_matches/leaderboard.html"

    def get_context_data(self, **kwargs):
        from vinosports.betting.models import UserStats

        ctx = super().get_context_data(**kwargs)
        ctx["leaderboard"] = UserStats.objects.select_related("user").order_by(
            "-net_profit"
        )[:50]
        return ctx


class LeaderboardPartialView(LeaderboardView):
    template_name = "worldcup_matches/partials/leaderboard_body.html"
