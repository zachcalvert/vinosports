from django.views.generic import TemplateView

from worldcup.matches.models import Match


class OddsBoardView(TemplateView):
    template_name = "worldcup_betting/odds_board.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        upcoming = (
            Match.objects.filter(
                status__in=[Match.Status.SCHEDULED, Match.Status.TIMED]
            )
            .select_related("home_team", "away_team", "stage", "group")
            .order_by("kickoff")
        )

        matches_with_odds = []
        for match in upcoming:
            odds = match.odds.first()
            matches_with_odds.append({"match": match, "odds": odds})

        ctx["matches_with_odds"] = matches_with_odds
        return ctx


class OddsBoardPartialView(OddsBoardView):
    template_name = "worldcup_betting/partials/odds_board_body.html"
