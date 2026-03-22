"""Bot registry — maps bot accounts to their strategy classes."""

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

BOT_PROFILES = [
    # ── Core strategy bots ──────────────────────────────────────────
    {
        "email": "frontrunner@bots.eplbets.local",
        "display_name": "ChalkEater",
        "strategy": FrontrunnerStrategy,
        "avatar_icon": "trophy",
        "avatar_bg": "#4f46e5",
    },
    {
        "email": "underdog@bots.eplbets.local",
        "display_name": "heartbreak_fc",
        "strategy": UnderdogStrategy,
        "avatar_icon": "wolf",
        "avatar_bg": "#dc2626",
    },
    {
        "email": "parlaypete@bots.eplbets.local",
        "display_name": "parlay_graveyard",
        "strategy": ParlayStrategy,
        "avatar_icon": "crown",
        "avatar_bg": "#d97706",
    },
    {
        "email": "drawdoctor@bots.eplbets.local",
        "display_name": "nil_nil_merchant",
        "strategy": DrawSpecialistStrategy,
        "avatar_icon": "target",
        "avatar_bg": "#0891b2",
    },
    {
        "email": "valuehunter@bots.eplbets.local",
        "display_name": "xG_is_real",
        "strategy": ValueHunterStrategy,
        "avatar_icon": "lightning",
        "avatar_bg": "#059669",
    },
    {
        "email": "chaoscharlie@bots.eplbets.local",
        "display_name": "VibesOnly",
        "strategy": ChaosAgentStrategy,
        "avatar_icon": "flame",
        "avatar_bg": "#ea580c",
    },
    {
        "email": "allinalice@bots.eplbets.local",
        "display_name": "FULL_SEND_FC",
        "strategy": AllInAliceStrategy,
        "avatar_icon": "rocket",
        "avatar_bg": "#db2777",
    },
    # ── Homer bots ──────────────────────────────────────────────────
    {
        "email": "arsenal-homer@bots.eplbets.local",
        "display_name": "trust_the_process",
        "strategy": HomerBotStrategy,
        "team_tla": "ARS",
        "avatar_icon": "shield",
        "avatar_bg": "#EF0107",
    },
    {
        "email": "chelsea-homer@bots.eplbets.local",
        "display_name": "BlueSzn",
        "strategy": HomerBotStrategy,
        "team_tla": "CHE",
        "avatar_icon": "gem",
        "avatar_bg": "#034694",
    },
    {
        "email": "liverpool-homer@bots.eplbets.local",
        "display_name": "never_walk_alone",
        "strategy": HomerBotStrategy,
        "team_tla": "LIV",
        "avatar_icon": "heart",
        "avatar_bg": "#C8102E",
    },
    {
        "email": "manutd-homer@bots.eplbets.local",
        "display_name": "GlazersOut99",
        "strategy": HomerBotStrategy,
        "team_tla": "MUN",
        "avatar_icon": "fire",
        "avatar_bg": "#DA291C",
    },
    {
        "email": "mancity-homer@bots.eplbets.local",
        "display_name": "oil_money_fc",
        "strategy": HomerBotStrategy,
        "team_tla": "MCI",
        "avatar_icon": "trophy",
        "avatar_bg": "#6CABDD",
    },
    {
        "email": "spurs-homer@bots.eplbets.local",
        "display_name": "spursy_forever",
        "strategy": HomerBotStrategy,
        "team_tla": "TOT",
        "avatar_icon": "target",
        "avatar_bg": "#132257",
    },
    {
        "email": "newcastle-homer@bots.eplbets.local",
        "display_name": "ToonArmyMagpie",
        "strategy": HomerBotStrategy,
        "team_tla": "NEW",
        "avatar_icon": "bird",
        "avatar_bg": "#241F20",
    },
    {
        "email": "everton-homer@bots.eplbets.local",
        "display_name": "EvertonTilIDie",
        "strategy": HomerBotStrategy,
        "team_tla": "EVE",
        "avatar_icon": "anchor",
        "avatar_bg": "#003399",
    },
]

# Lookup: email -> full profile dict
PROFILE_MAP = {p["email"]: p for p in BOT_PROFILES}

# Lookup: email -> strategy class (convenience)
STRATEGY_MAP = {p["email"]: p["strategy"] for p in BOT_PROFILES}

# Lookup: BotProfile.StrategyType value -> strategy class
# (imported lazily in get_strategy_for_bot, but the mapping is static)
STRATEGY_TYPE_TO_CLASS = {
    "frontrunner": FrontrunnerStrategy,
    "underdog": UnderdogStrategy,
    "parlay": ParlayStrategy,
    "draw_specialist": DrawSpecialistStrategy,
    "value_hunter": ValueHunterStrategy,
    "chaos_agent": ChaosAgentStrategy,
    "all_in_alice": AllInAliceStrategy,
    "homer": HomerBotStrategy,
}


def get_strategy_for_bot(user):
    """Return an instantiated strategy for the given bot user, or None.

    Reads strategy_type and team_tla from the database-backed BotProfile.
    Falls back to the hardcoded PROFILE_MAP for bots that haven't been
    migrated yet.
    """
    from bots.models import BotProfile

    bp = getattr(user, "bot_profile", None)
    if bp is None:
        try:
            bp = BotProfile.objects.get(user=user)
        except BotProfile.DoesNotExist:
            bp = None

    if bp:
        cls = STRATEGY_TYPE_TO_CLASS.get(bp.strategy_type)
        if cls is None:
            return None
        if cls is HomerBotStrategy:
            from matches.models import Team

            team = Team.objects.filter(tla=bp.team_tla).first()
            if not team:
                return None
            return HomerBotStrategy(team_id=team.pk)
        return cls()

    # Fallback to hardcoded registry (pre-migration compatibility)
    profile = PROFILE_MAP.get(user.email)
    if not profile:
        return None

    cls = profile["strategy"]
    if cls is HomerBotStrategy:
        from matches.models import Team

        team = Team.objects.filter(tla=profile["team_tla"]).first()
        if not team:
            return None
        return HomerBotStrategy(team_id=team.pk)

    return cls()
