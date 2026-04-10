"""World Cup league adapter for the centralized bot comment pipeline."""

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
    "world cup",
    "worldcup",
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
    "moneyline",
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
    "group stage",
    "knockout",
    "quarter-final",
    "semi-final",
    "final",
    "tournament",
    "confederation",
    "national team",
}


class WorldCupAdapter(LeagueAdapter):
    league = "worldcup"
    keywords = FOOTBALL_KEYWORDS
    reply_affinities = {}
    active_field = "active_in_worldcup"

    def get_bot_comment_model(self):
        from worldcup.bots.models import BotComment

        return BotComment

    def get_comment_model(self):
        from worldcup.discussions.models import Comment

        return Comment

    def get_bet_slip_model(self):
        from worldcup.betting.models import BetSlip

        return BetSlip

    def get_event_fk_name(self):
        return "match"

    def build_match_context(self, match):
        from worldcup.matches.models import MatchNotes

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
        if match.group:
            header_lines.append(f"Group {match.group.letter}")
        if match.venue:
            header_lines.append(f"Venue: {match.venue}, {match.city}")

        home_short = home.tla or home.short_name or ""
        away_short = away.tla or away.short_name or ""

        team_terms = {
            home.name.lower(),
            away.name.lower(),
            (home.short_name or "").lower(),
            (away.short_name or "").lower(),
            (home.tla or "").lower(),
            (away.tla or "").lower(),
            (home.country_code or "").lower(),
            (away.country_code or "").lower(),
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
            league="worldcup",
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
        from worldcup.matches.models import Team

        team = Team.objects.filter(country_code=identifier).first()
        if not team:
            return None
        return (
            team.name.lower(),
            (team.short_name or "").lower(),
            (team.tla or "").lower(),
            (team.country_code or "").lower(),
        )

    def get_homer_identifier(self, profile):
        return profile.worldcup_country_code

    def is_bot_relevant(self, profile, match):
        st = profile.strategy_type
        if st == StrategyType.HOMER:
            code = profile.worldcup_country_code
            if code:
                home_cc = getattr(match.home_team, "country_code", None)
                away_cc = getattr(match.away_team, "country_code", None)
                return home_cc == code or away_cc == code
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


worldcup_adapter = WorldCupAdapter()
