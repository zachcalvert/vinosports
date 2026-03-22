from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Case, Count, IntegerField, Min, Q, Sum, Value, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.generic import DetailView, TemplateView, View

from betting.forms import PlaceBetForm
from betting.models import BetSlip
from vinosports.betting.leaderboard import BOARD_TYPES, get_leaderboard_entries, get_user_rank
from matches.forms import MatchNotesForm
from matches.models import Match, MatchNotes, Odds, Standing
from matches.services import fetch_match_hype_data


def _get_default_matchday(season):
    """Return the best default matchday: next upcoming, or most recent."""
    today = timezone.now().date()
    next_match = (
        Match.objects.filter(season=season, kickoff__date__gte=today)
        .order_by("kickoff")
        .first()
    )
    if next_match:
        return next_match.matchday
    prev_match = (
        Match.objects.filter(season=season, kickoff__date__lt=today)
        .order_by("-kickoff")
        .first()
    )
    return prev_match.matchday if prev_match else 1


def _get_matches_with_odds(season, matchday):
    """Return match list for a matchday with best odds annotated."""
    unplayed_statuses = [Match.Status.SCHEDULED, Match.Status.TIMED]
    matches = (
        Match.objects.filter(season=season, matchday=matchday)
        .select_related("home_team", "away_team")
        .annotate(
            unplayed_priority=Case(
                When(status__in=unplayed_statuses, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("unplayed_priority", "kickoff")
    )
    match_list = list(matches)
    match_ids = [m.pk for m in match_list]

    best_odds = (
        Odds.objects.filter(match_id__in=match_ids)
        .values("match_id")
        .annotate(
            best_home=Min("home_win"),
            best_draw=Min("draw"),
            best_away=Min("away_win"),
        )
    )
    odds_map = {o["match_id"]: o for o in best_odds}

    for match in match_list:
        odds = odds_map.get(match.pk, {})
        match.best_home_odds = odds.get("best_home")
        match.best_draw_odds = odds.get("best_draw")
        match.best_away_odds = odds.get("best_away")

    return match_list


class DashboardView(TemplateView):
    template_name = "matches/dashboard.html"

    def get_template_names(self):
        if self.request.htmx:
            return ["matches/partials/fixture_list_htmx.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = settings.CURRENT_SEASON
        matchdays = list(range(1, 39))
        default_matchday = _get_default_matchday(season)

        try:
            matchday = int(self.request.GET.get("matchday", default_matchday))
        except (ValueError, TypeError):
            matchday = default_matchday

        match_list = _get_matches_with_odds(season, matchday)

        ctx["matches"] = match_list
        ctx["matchday"] = matchday
        ctx["matchdays"] = matchdays
        ctx["current_matchday"] = matchday

        # HTMX partial requests only need match data
        if self.request.htmx:
            return ctx

        ctx["leaderboard"] = get_leaderboard_entries()
        ctx["user_rank"] = get_user_rank(self.request.user, ctx["leaderboard"])
        ctx["leaderboard_rendered_at"] = timezone.now()
        # League table preview (top 8 teams)
        ctx["standings"] = (
            Standing.objects.filter(season=settings.CURRENT_SEASON)
            .select_related("team")
            .order_by("position")[:8]
        )

        return ctx


class LeaderboardPartialView(TemplateView):
    template_name = "matches/partials/leaderboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["leaderboard"] = get_leaderboard_entries()
        ctx["user_rank"] = get_user_rank(self.request.user, ctx["leaderboard"])
        ctx["leaderboard_rendered_at"] = timezone.now()
        return ctx


class LeaderboardView(TemplateView):
    template_name = "matches/leaderboard.html"

    def _get_board_type(self):
        board_type = self.request.GET.get("type", "balance")
        return board_type if board_type in BOARD_TYPES else "balance"

    def get_template_names(self):
        if self.request.htmx:
            return ["matches/partials/leaderboard_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        board_type = self._get_board_type()
        ctx["leaderboard"] = get_leaderboard_entries(limit=None, board_type=board_type)
        ctx["user_rank"] = get_user_rank(
            self.request.user, ctx["leaderboard"], board_type=board_type
        )
        ctx["board_type"] = board_type
        ctx["board_types"] = BOARD_TYPES
        return ctx



class LeagueTableView(TemplateView):
    template_name = "matches/league_table.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["standings"] = (
            Standing.objects.filter(season=settings.CURRENT_SEASON)
            .select_related("team")
            .order_by("position")
        )
        ctx["season"] = settings.CURRENT_SEASON
        return ctx


def _get_hype_context(match):
    """Build community sentiment and standing data for the hype card."""
    season = settings.CURRENT_SEASON

    # Community sentiment — live aggregation from BetSlip
    rows = (
        BetSlip.objects.filter(match=match)
        .values("selection")
        .annotate(count=Count("id"))
    )
    counts = {r["selection"]: r["count"] for r in rows}
    total = sum(counts.values())

    sentiment = None
    if total:
        home_pct = round(counts.get(BetSlip.Selection.HOME_WIN, 0) / total * 100)
        draw_pct = round(counts.get(BetSlip.Selection.DRAW, 0) / total * 100)
        away_pct = 100 - home_pct - draw_pct  # avoids rounding drift
        most_popular_count = max(counts.values())
        most_popular_label = next(
            label
            for sel, label in BetSlip.Selection.choices
            if counts.get(sel, 0) == most_popular_count
        )
        sentiment = {
            "total": total,
            "home_pct": home_pct,
            "draw_pct": draw_pct,
            "away_pct": away_pct,
            "most_popular": most_popular_label,
        }

    # Standings for key stats
    standings = Standing.objects.filter(
        season=season,
        team__in=[match.home_team, match.away_team],
    ).select_related("team")
    standing_map = {s.team_id: s for s in standings}

    return {
        "sentiment": sentiment,
        "home_standing": standing_map.get(match.home_team_id),
        "away_standing": standing_map.get(match.away_team_id),
    }


def _get_recap_context(match, home_standing, away_standing):
    """Build result context and betting outcome data for the recap card."""
    # Determine actual result
    if match.home_score is not None and match.away_score is not None:
        if match.home_score > match.away_score:
            actual_result = "HOME_WIN"
            actual_result_label = "Home Win"
            winner = match.home_team
            loser = match.away_team
            winner_standing = home_standing
            loser_standing = away_standing
        elif match.home_score < match.away_score:
            actual_result = "AWAY_WIN"
            actual_result_label = "Away Win"
            winner = match.away_team
            loser = match.home_team
            winner_standing = away_standing
            loser_standing = home_standing
        else:
            actual_result = "DRAW"
            actual_result_label = "Draw"
            winner = None
            loser = None
            winner_standing = None
            loser_standing = None
    else:
        return {}

    # Build result context headline
    home_name = match.home_team.short_name or match.home_team.name
    away_name = match.away_team.short_name or match.away_team.name
    score_line = f"{match.home_score}-{match.away_score}"

    is_upset = False
    if winner and winner_standing and loser_standing:
        is_upset = winner_standing.position > loser_standing.position
        winner_name = winner.short_name or winner.name
        loser_name = loser.short_name or loser.name
        if is_upset:
            headline = f"{winner_name} pull off the upset against {loser_name} ({score_line})"
        else:
            headline = f"{winner_name} beat {loser_name} ({score_line})"
    elif winner:
        winner_name = winner.short_name or winner.name
        loser_name = loser.short_name or loser.name
        headline = f"{winner_name} beat {loser_name} ({score_line})"
    else:
        headline = f"Honours even between {home_name} and {away_name} ({score_line})"

    result_context = {
        "headline": headline,
        "is_upset": is_upset,
        "score_line": score_line,
    }

    # Betting outcome aggregates
    agg = BetSlip.objects.filter(match=match).aggregate(
        total_bets=Count("id"),
        winners=Count("id", filter=Q(status=BetSlip.Status.WON)),
        losers=Count("id", filter=Q(status=BetSlip.Status.LOST)),
        voided=Count("id", filter=Q(status=BetSlip.Status.VOID)),
        total_staked=Sum("stake"),
        total_won_payout=Sum("payout", filter=Q(status=BetSlip.Status.WON)),
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


class MatchDetailView(DetailView):
    model = Match
    template_name = "matches/match_detail.html"
    context_object_name = "match"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Match.objects.select_related("home_team", "away_team").prefetch_related(
            "odds"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        match = self.object
        odds_qs = match.odds.all().order_by("bookmaker")
        odds_list = list(odds_qs)

        if odds_list:
            best_home = min(o.home_win for o in odds_list)
            best_draw = min(o.draw for o in odds_list)
            best_away = min(o.away_win for o in odds_list)
            latest_odds_refresh = max(o.fetched_at for o in odds_list)
        else:
            best_home = best_draw = best_away = None
            latest_odds_refresh = None

        ctx["odds"] = odds_list
        ctx["best_home"] = best_home
        ctx["best_draw"] = best_draw
        ctx["best_away"] = best_away
        ctx["latest_odds_refresh"] = latest_odds_refresh
        ctx["match_updated_at"] = match.updated_at

        # Bet form for authenticated users
        if self.request.user.is_authenticated:
            ctx["form"] = PlaceBetForm()

        # Status card is lazy-loaded via HTMX for faster initial render
        ctx["has_status_card"] = match.status in (
            Match.Status.SCHEDULED,
            Match.Status.TIMED,
            Match.Status.IN_PLAY,
            Match.Status.PAUSED,
            Match.Status.FINISHED,
        )

        # Match notes form (superusers only)
        if self.request.user.is_authenticated and self.request.user.is_superuser:
            try:
                notes = match.notes
            except MatchNotes.DoesNotExist:
                notes = None
            ctx["match_notes_form"] = MatchNotesForm(instance=notes)
            ctx["match_notes"] = notes

        # Standings for header league-position display
        standings = Standing.objects.filter(
            season=settings.CURRENT_SEASON,
            team__in=[match.home_team, match.away_team],
        ).select_related("team")
        standing_map = {s.team_id: s for s in standings}
        ctx["home_standing"] = standing_map.get(match.home_team_id)
        ctx["away_standing"] = standing_map.get(match.away_team_id)

        return ctx


class MatchStatusCardPartialView(DetailView):
    """Lazy-loaded status card (hype / live / recap) for HTMX."""

    model = Match
    context_object_name = "match"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Match.objects.select_related("home_team", "away_team").prefetch_related(
            "odds"
        )

    def get_template_names(self):
        match = self.object
        if match.status in (Match.Status.SCHEDULED, Match.Status.TIMED):
            return ["matches/partials/hype_card.html"]
        elif match.status in (Match.Status.IN_PLAY, Match.Status.PAUSED):
            return ["matches/partials/live_card.html"]
        elif match.status == Match.Status.FINISHED:
            return ["matches/partials/recap_card.html"]
        return ["matches/partials/hype_card.html"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        match = self.object

        ctx["match_stats"] = fetch_match_hype_data(match)
        hype_ctx = _get_hype_context(match)
        ctx.update(hype_ctx)

        if match.status == Match.Status.FINISHED:
            ctx.update(
                _get_recap_context(
                    match,
                    hype_ctx.get("home_standing"),
                    hype_ctx.get("away_standing"),
                )
            )

        return ctx


class MatchNotesView(UserPassesTestMixin, View):
    """HTMX endpoint for superusers to create/update match notes."""

    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, slug):
        match = get_object_or_404(Match, slug=slug)
        notes, _created = MatchNotes.objects.get_or_create(
            match=match, defaults={"body": ""}
        )

        form = MatchNotesForm(request.POST, instance=notes)
        saved = False
        status = 200
        if form.is_valid():
            form.save()
            notes.refresh_from_db()
            form = MatchNotesForm(instance=notes)
            saved = True
        else:
            status = 400

        html = render_to_string(
            "matches/partials/match_notes_panel.html",
            {"match": match, "match_notes_form": form, "match_notes": notes, "saved": saved},
            request=request,
        )
        return HttpResponse(html, status=status)


class MatchOddsPartialView(MatchDetailView):
    """Returns just the odds table body for HTMX polling."""

    template_name = "matches/partials/odds_table_body.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)
