"""NBA league adapter for the centralized bot comment pipeline."""

from vinosports.bots.comment_pipeline import LeagueAdapter, MatchContext
from vinosports.bots.models import StrategyType

BASKETBALL_KEYWORDS = {
    "game",
    "win",
    "loss",
    "odds",
    "bet",
    "nba",
    "quarter",
    "half",
    "overtime",
    "score",
    "points",
    "spread",
    "moneyline",
    "parlay",
    "stake",
    "payout",
    "underdog",
    "favorite",
    "favourite",
    "upset",
    "blowout",
    "clutch",
    "choke",
    "fraud",
    "frauds",
    "lock",
    "locks",
    "chalk",
    "degen",
    "comeback",
    "dunk",
    "three",
    "triple",
    "double",
    "rebound",
    "assist",
    "block",
    "steal",
    "playoff",
    "playoffs",
    "seed",
    "conference",
    "series",
}


class NBAAdapter(LeagueAdapter):
    league = "nba"
    keywords = BASKETBALL_KEYWORDS
    reply_affinities = {}
    active_field = "active_in_nba"

    def get_bot_comment_model(self):
        from nba.bots.models import BotComment

        return BotComment

    def get_comment_model(self):
        from nba.discussions.models import Comment

        return Comment

    def get_bet_slip_model(self):
        from nba.betting.models import BetSlip

        return BetSlip

    def get_event_fk_name(self):
        return "game"

    def build_match_context(self, game):
        from nba.games.models import GameNotes, GameStats

        home = game.home_team
        away = game.away_team

        header_lines = [
            f"Game: {home.name} vs {away.name}",
        ]
        if game.tip_off:
            header_lines.append(
                f"Tip-off: {game.tip_off.strftime('%a %d %b, %H:%M UTC')}"
            )
        if home.abbreviation and away.abbreviation and game.arena:
            header_lines.append(f"Arena: {game.arena}")

        home_short = home.short_name or home.abbreviation or ""
        away_short = away.short_name or away.abbreviation or ""

        team_terms = {
            home.name.lower(),
            away.name.lower(),
            (home.short_name or "").lower(),
            (away.short_name or "").lower(),
            (home.abbreviation or "").lower(),
            (away.abbreviation or "").lower(),
        }
        team_terms.discard("")

        # Odds
        odds_lines = []
        from nba.games.models import Odds

        odds = Odds.objects.filter(game=game).order_by("-fetched_at").first()
        if odds:
            if odds.home_moneyline is not None and odds.away_moneyline is not None:
                odds_lines.append(
                    f"Moneyline: {home.short_name} {odds.home_moneyline:+d}"
                    f" | {away.short_name} {odds.away_moneyline:+d}"
                )
            if odds.spread_line is not None:
                odds_lines.append(f"Spread: {home.short_name} {odds.spread_line:+g}")
        odds_line = "\n".join(odds_lines)

        # H2H and form
        stats_lines = []
        try:
            stats = GameStats.objects.get(game=game)
            if stats.h2h:
                stats_lines.append(f"H2H: {stats.h2h}")
            if stats.form:
                stats_lines.append(f"Form: {stats.form}")
        except GameStats.DoesNotExist:
            pass

        # Game notes
        notes = ""
        try:
            gn = GameNotes.objects.get(game=game)
            if gn.body.strip():
                notes = gn.body.strip()
        except GameNotes.DoesNotExist:
            pass

        # Score line
        score_line = ""
        if game.home_score is not None:
            score_line = f"Final score: {home.name} {game.home_score}-{game.away_score} {away.name}"

        return MatchContext(
            event_id=game.pk,
            league="nba",
            home_team=home.name,
            away_team=away.name,
            home_team_short=home_short,
            away_team_short=away_short,
            header_lines=header_lines,
            odds_line=odds_line,
            stats_lines=stats_lines,
            notes=notes,
            score_line=score_line,
            team_terms=team_terms,
        )

    def resolve_homer_terms(self, identifier):
        from nba.games.models import Team

        team = Team.objects.filter(abbreviation=identifier).first()
        if not team:
            return None
        return (
            team.name.lower(),
            (team.short_name or "").lower(),
            (team.abbreviation or "").lower(),
        )

    def get_homer_identifier(self, profile):
        return profile.nba_team_abbr

    def is_bot_relevant(self, profile, game):
        st = profile.strategy_type
        if st == StrategyType.HOMER:
            abbr = profile.nba_team_abbr
            if abbr:
                return (
                    getattr(game.home_team, "abbreviation", None) == abbr
                    or getattr(game.away_team, "abbreviation", None) == abbr
                )
            return False
        elif st in (
            StrategyType.FRONTRUNNER,
            StrategyType.UNDERDOG,
            StrategyType.PARLAY,
            StrategyType.CHAOS_AGENT,
            StrategyType.ALL_IN_ALICE,
        ):
            return True
        return False


nba_adapter = NBAAdapter()
