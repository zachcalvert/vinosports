"""EPL league adapter for the centralized bot comment pipeline."""

from vinosports.bots.comment_pipeline import LeagueAdapter, MatchContext
from vinosports.bots.models import StrategyType

# Which bots are likely to reply to which — email -> list of emails they have beef with.
BOT_REPLY_AFFINITIES = {
    "valuehunter@bots.eplbets.local": [
        "chaoscharlie@bots.eplbets.local",  # process vs vibes
        "allinalice@bots.eplbets.local",  # EV vs YOLO
    ],
    "frontrunner@bots.eplbets.local": [
        "underdog@bots.eplbets.local",  # chalk vs heart
    ],
    "underdog@bots.eplbets.local": [
        "frontrunner@bots.eplbets.local",  # mutual disdain
        "allinalice@bots.eplbets.local",  # "wow you backed City"
    ],
    "parlaypete@bots.eplbets.local": [
        "allinalice@bots.eplbets.local",  # single bet resentment
        "frontrunner@bots.eplbets.local",  # "congrats on your boring bet"
    ],
    "chaoscharlie@bots.eplbets.local": [
        "valuehunter@bots.eplbets.local",  # suspicious of the stats guy
    ],
    "drawdoctor@bots.eplbets.local": [
        "frontrunner@bots.eplbets.local",  # dismissive of certainty
        "allinalice@bots.eplbets.local",  # dismissive of YOLO
    ],
    "allinalice@bots.eplbets.local": [
        "valuehunter@bots.eplbets.local",  # hates the process talk
        "drawdoctor@bots.eplbets.local",  # boring draws are cowardice
    ],
}

FOOTBALL_KEYWORDS = {
    "match",
    "goal",
    "goals",
    "win",
    "draw",
    "loss",
    "nil",
    "odds",
    "bet",
    "form",
    "league",
    "premier",
    "epl",
    "kickoff",
    "kick",
    "half",
    "full",
    "time",
    "score",
    "clean sheet",
    "derby",
    "relegation",
    "promoted",
    "champions",
    "top",
    "bottom",
    "table",
    "points",
    "gd",
    "xg",
    "expected",
    "parlay",
    "stake",
    "payout",
    "underdog",
    "favourite",
    "favorite",
    "upset",
    "bottle",
    "bottled",
    "fraud",
    "frauds",
    "merchant",
    "tax",
    "copium",
    "scenes",
    "inject",
    "lock",
    "locks",
    "chalk",
    "degen",
    "comeback",
    "banger",
    "shithouse",
    "masterclass",
}


class EPLAdapter(LeagueAdapter):
    league = "epl"
    keywords = FOOTBALL_KEYWORDS
    reply_affinities = BOT_REPLY_AFFINITIES
    active_field = "active_in_epl"

    def get_bot_comment_model(self):
        from epl.bots.models import BotComment

        return BotComment

    def get_comment_model(self):
        from epl.discussions.models import Comment

        return Comment

    def get_bet_slip_model(self):
        from epl.betting.models import BetSlip

        return BetSlip

    def get_event_fk_name(self):
        return "match"

    def build_match_context(self, match):
        from epl.bots.services import get_best_odds_map
        from epl.matches.models import MatchNotes, MatchStats

        home = match.home_team
        away = match.away_team

        # Header lines
        header_lines = [
            f"Match: {home.name} vs {away.name}",
            f"Kickoff: {match.kickoff.strftime('%a %d %b, %H:%M UTC')} | Matchday {match.matchday}",
        ]
        if home.venue:
            header_lines.append(f"Venue: {home.venue}")

        # Team terms for filter
        home_short = home.short_name or ""
        away_short = away.short_name or ""
        home_tla = home.tla or ""
        away_tla = away.tla or ""

        team_terms = {
            home.name.lower(),
            away.name.lower(),
            home_short.lower(),
            away_short.lower(),
            home_tla.lower(),
            away_tla.lower(),
        }
        team_terms.discard("")

        # Odds
        odds_line = ""
        odds_map = get_best_odds_map([match.pk])
        match_odds = odds_map.get(match.pk, {})
        if match_odds:
            odds_line = (
                f"Odds: {home_short or home_tla} {match_odds.get('home_win', '?')}"
                f" | Draw {match_odds.get('draw', '?')}"
                f" | {away_short or away_tla} {match_odds.get('away_win', '?')}"
            )

        # H2H and form
        stats_lines = []
        try:
            stats = MatchStats.objects.get(match=match)
            h2h = stats.h2h_summary_json
            if h2h:
                stats_lines.append(
                    f"H2H (last {h2h.get('total', '?')}): "
                    f"{home_short or home_tla} {h2h.get('home_wins', 0)}W "
                    f"- {h2h.get('draws', 0)}D - "
                    f"{away_short or away_tla} {h2h.get('away_wins', 0)}W"
                )
            if stats.home_form_json:
                form_str = " ".join(
                    r.get("result", "?") for r in stats.home_form_json[:5]
                )
                stats_lines.append(f"{home_short or home_tla} form: {form_str}")
            if stats.away_form_json:
                form_str = " ".join(
                    r.get("result", "?") for r in stats.away_form_json[:5]
                )
                stats_lines.append(f"{away_short or away_tla} form: {form_str}")
        except MatchStats.DoesNotExist:
            pass

        # Match notes
        notes = ""
        try:
            mn = MatchNotes.objects.get(match=match)
            if mn.body.strip():
                notes = mn.body.strip()
        except MatchNotes.DoesNotExist:
            pass

        # Score line for post-match
        score_line = ""
        if match.home_score is not None:
            score_line = f"Final score: {home.name} {match.home_score}-{match.away_score} {away.name}"

        return MatchContext(
            event_id=match.pk,
            league="epl",
            home_team=home.name,
            away_team=away.name,
            home_team_short=home_short or home_tla,
            away_team_short=away_short or away_tla,
            header_lines=header_lines,
            odds_line=odds_line,
            stats_lines=stats_lines,
            notes=notes,
            score_line=score_line,
            team_terms=team_terms,
        )

    def resolve_homer_terms(self, identifier):
        from epl.matches.models import Team

        team = Team.objects.filter(tla=identifier).first()
        if not team:
            return None
        return (
            team.name.lower(),
            (team.short_name or "").lower(),
            (team.tla or "").lower(),
        )

    def get_homer_identifier(self, profile):
        return profile.epl_team_tla

    def is_bot_relevant(self, profile, match, match_odds=None):
        from epl.matches.models import Odds

        if match_odds is None:
            from epl.bots.services import get_best_odds_map

            odds_map = get_best_odds_map([match.pk])
            match_odds = odds_map.get(match.pk, {})

        home = match_odds.get("home_win")
        draw = match_odds.get("draw")
        away = match_odds.get("away_win")

        st = profile.strategy_type
        if st == StrategyType.FRONTRUNNER:
            if home and away:
                return min(home, away) < 1.80
        elif st == StrategyType.UNDERDOG:
            if home and away:
                return max(home, away) >= 3.00
        elif st == StrategyType.DRAW_SPECIALIST:
            if draw:
                return 2.80 <= float(draw) <= 3.80
        elif st == StrategyType.VALUE_HUNTER:
            bookmaker_count = Odds.objects.filter(match=match).count()
            return bookmaker_count >= 2
        elif st in (
            StrategyType.PARLAY,
            StrategyType.CHAOS_AGENT,
            StrategyType.ALL_IN_ALICE,
        ):
            return True
        elif st == StrategyType.HOMER:
            tla = profile.epl_team_tla
            if tla:
                return (
                    getattr(match.home_team, "tla", None) == tla
                    or getattr(match.away_team, "tla", None) == tla
                )
            return False

        return False


# Module-level singleton for convenience
epl_adapter = EPLAdapter()
