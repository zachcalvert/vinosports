"""Bot registry — maps strategy types to strategy classes.

Reads strategy_type from the global BotProfile and resolves to the
league-specific EPL strategy implementation.
"""

from bots.strategies import (
    AllInAliceStrategy,
    ChaosAgentStrategy,
    DrawSpecialistStrategy,
    FrontrunnerStrategy,
    HomerBotStrategy,
    ParlayStrategy,
    UnderdogStrategy,
    ValueHunterStrategy,
)
from vinosports.bots.models import StrategyType

# Lookup: StrategyType value -> EPL strategy class
STRATEGY_TYPE_TO_CLASS = {
    StrategyType.FRONTRUNNER: FrontrunnerStrategy,
    StrategyType.UNDERDOG: UnderdogStrategy,
    StrategyType.PARLAY: ParlayStrategy,
    StrategyType.DRAW_SPECIALIST: DrawSpecialistStrategy,
    StrategyType.VALUE_HUNTER: ValueHunterStrategy,
    StrategyType.CHAOS_AGENT: ChaosAgentStrategy,
    StrategyType.ALL_IN_ALICE: AllInAliceStrategy,
    StrategyType.HOMER: HomerBotStrategy,
}


def get_strategy_for_bot(user):
    """Return an instantiated strategy for the given bot user, or None.

    Reads strategy_type and epl_team_tla from the global BotProfile.
    """
    from vinosports.bots.models import BotProfile

    try:
        bp = user.bot_profile
    except BotProfile.DoesNotExist:
        return None

    if not bp.active_in_epl:
        return None

    cls = STRATEGY_TYPE_TO_CLASS.get(bp.strategy_type)
    if cls is None:
        return None

    if cls is HomerBotStrategy:
        from matches.models import Team

        team = Team.objects.filter(tla=bp.epl_team_tla).first()
        if not team:
            return None
        return HomerBotStrategy(team_id=team.pk)

    return cls()
