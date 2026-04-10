"""UCL league adapter for the centralized bot comment pipeline."""

from vinosports.bots.comment_pipeline import LeagueAdapter, MatchContext
from vinosports.bots.models import StrategyType

FOOTBALL_KEYWORDS = {
    "match",
    "game",
    "win",
    "loss",
    "draw",
    "odds",
    "bet",
    "champions league",
    "ucl",
    "goal",
    "goals",
    "penalty",
    "penalties",
    "shootout",
    "extra time",
    "half",
    "fulltime",
    "score",
    "points",
    "parlay",
    "stake",
    "payout",
    "underdog",
    "favourite",
    "favorite",
    "upset",
    "clean sheet",
    "tackle",
    "foul",
    "offside",
    "red card",
    "yellow card",
    "league phase",
    "knockout",
    "quarter-final",
    "semi-final",
    "final",
    "tournament",
    "aggregate",
    "two-leg",
    "away goals",
}


class UCLAdapter(LeagueAdapter):
    league = "ucl"
    keywords = FOOTBALL_KEYWORDS
    reply_affinities = {}
    active_field = "active_in_ucl"

    def get_bot_comment_model(self):
        from ucl.bots.models import BotComment

        return BotComment

    def get_comment_model(self):
        from ucl.discussions.models import Comment

        return Comment

    def get_bet_slip_model(self):
        from ucl.betting.models import BetSlip

        return BetSlip

    def get_event_fk_name(self):
        return "match"

    def build_match_context(self, match):
        from ucl.matches.models import MatchNotes

        home = match.home_team
        away = match.away_team

        header_lines = [
            f"Match: {home.name} vs {away.name}",
        ]
        if match.kickoff:
            header_lines.append(
                f"Kickoff: {match.kickoff.strftime('%a %d %b, %H:%M UTC')}"
            )
        if match.stage:
            header_lines.append(f"Stage: {match.stage.name}")
        if match.is_knockout and match.leg:
            header_lines.append(f"Leg {match.leg}")
        if match.venue_name:
            city = f", {match.venue_city}" if match.venue_city else ""
            header_lines.append(f"Venue: {match.venue_name}{city}")

        home_short = home.tla or home.short_name or ""
        away_short = away.tla or away.short_name or ""

        team_terms = {
            home.name.lower(),
            away.name.lower(),
            (home.short_name or "").lower(),
            (away.short_name or "").lower(),
            (home.tla or "").lower(),
            (away.tla or "").lower(),
        }
        team_terms.discard("")

        # Odds
        odds_line = ""
        odds = match.odds.order_by("-fetched_at").first()
        if odds:
            odds_line = (
                f"Odds: {home_short} win {odds.home_win} "
                f"| Draw {odds.draw} "
                f"| {away_short} win {odds.away_win}"
            )

        # Match notes
        notes = ""
        try:
            mn = MatchNotes.objects.get(match=match)
            if mn.body.strip():
                notes = mn.body.strip()
        except MatchNotes.DoesNotExist:
            pass

        # Score line
        score_line = ""
        if match.home_score is not None:
            score_line = f"Final score: {home.name} {match.home_score}-{match.away_score} {away.name}"

        return MatchContext(
            event_id=match.pk,
            league="ucl",
            home_team=home.name,
            away_team=away.name,
            home_team_short=home_short,
            away_team_short=away_short,
            header_lines=header_lines,
            odds_line=odds_line,
            stats_lines=[],
            notes=notes,
            score_line=score_line,
            team_terms=team_terms,
        )

    def resolve_homer_terms(self, identifier):
        from ucl.matches.models import Team

        team = Team.objects.filter(tla=identifier).first()
        if not team:
            return None
        return (
            team.name.lower(),
            (team.short_name or "").lower(),
            (team.tla or "").lower(),
        )

    def get_homer_identifier(self, profile):
        return profile.ucl_team_tla

    def is_bot_relevant(self, profile, match):
        st = profile.strategy_type
        if st == StrategyType.HOMER:
            tla = profile.ucl_team_tla
            if tla:
                home_tla = getattr(match.home_team, "tla", None)
                away_tla = getattr(match.away_team, "tla", None)
                return home_tla == tla or away_tla == tla
            return False
        elif st in (
            StrategyType.FRONTRUNNER,
            StrategyType.UNDERDOG,
            StrategyType.CHAOS_AGENT,
            StrategyType.ALL_IN_ALICE,
            StrategyType.DRAW_SPECIALIST,
        ):
            return True
        return False


ucl_adapter = UCLAdapter()
