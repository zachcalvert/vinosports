from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig

# Each group: (group_name, app_label_slug, collapsed, [(app_label, object_name, display_name_override), ...])
# display_name_override is optional (use None to keep the model's verbose_name_plural)
ADMIN_GROUPS = [
    (
        "General",
        "general",
        False,
        [
            ("global_bots", "BotProfile", None),
            ("betting", "FeaturedParlay", None),
            ("core", "GlobalKnowledge", None),
            ("news", "NewsArticle", None),
            ("rewards", "Reward", None),
            ("reddit", "SubredditSnapshot", None),
            ("users", "User", None),
        ],
    ),
    (
        "Challenges",
        "challenges",
        False,
        [
            ("challenges", "ChallengeTemplate", None),
            ("challenges", "Challenge", None),
            ("challenges", "UserChallenge", None),
        ],
    ),
    (
        "Discussions",
        "discussions",
        False,
        [
            ("epl_bots", "BotComment", "EPL Bot Comments"),
            ("epl_discussions", "Comment", "EPL Human Comments"),
            ("nba_bots", "BotComment", "NBA Bot Comments"),
            ("nba_discussions", "Comment", "NBA Human Comments"),
            ("nfl_bots", "BotComment", "NFL Bot Comments"),
            ("nfl_discussions", "Comment", "NFL Human Comments"),
            ("ucl_bots", "BotComment", "UCL Bot Comments"),
            ("ucl_discussions", "Comment", "UCL Human Comments"),
            ("worldcup_bots", "BotComment", "World Cup Bot Comments"),
            ("worldcup_discussions", "Comment", "World Cup Human Comments"),
        ],
    ),
    (
        "Rewards",
        "rewards_admin",
        False,
        [
            ("rewards", "RewardDistribution", None),
            ("rewards", "RewardRule", None),
        ],
    ),
    (
        "EPL Bets",
        "epl_bets",
        True,
        [
            ("epl_betting", "BetSlip", None),
            ("epl_betting", "FuturesBet", None),
            ("epl_betting", "FuturesMarket", None),
            ("epl_betting", "FuturesOutcome", None),
            ("epl_betting", "Parlay", None),
        ],
    ),
    (
        "EPL Matches",
        "epl_matches_group",
        True,
        [
            ("epl_matches", "MatchNotes", None),
            ("epl_matches", "MatchStats", None),
            ("epl_matches", "Match", None),
            ("epl_matches", "Odds", None),
            ("epl_matches", "Standing", None),
            ("epl_matches", "Team", None),
        ],
    ),
    (
        "NBA Bets",
        "nba_bets",
        True,
        [
            ("nba_betting", "BetSlip", None),
            ("nba_betting", "FuturesBet", None),
            ("nba_betting", "FuturesMarket", None),
            ("nba_betting", "FuturesOutcome", None),
            ("nba_betting", "Parlay", None),
        ],
    ),
    (
        "NBA Games",
        "nba_games_group",
        True,
        [
            ("nba_games", "GameNotes", None),
            ("nba_games", "GameStats", None),
            ("nba_games", "Game", None),
            ("nba_games", "Odds", None),
            ("nba_games", "PlayerBoxScore", None),
            ("nba_games", "Player", None),
            ("nba_games", "Standing", None),
            ("nba_games", "Team", None),
        ],
    ),
    (
        "NFL Bets",
        "nfl_bets",
        True,
        [
            ("nfl_betting", "BetSlip", None),
            ("nfl_betting", "FuturesBet", None),
            ("nfl_betting", "FuturesMarket", None),
            ("nfl_betting", "FuturesOutcome", None),
            ("nfl_betting", "Odds", None),
            ("nfl_betting", "Parlay", None),
        ],
    ),
    (
        "NFL Games",
        "nfl_games_group",
        True,
        [
            ("nfl_games", "GameNotes", None),
            ("nfl_games", "GameStats", None),
            ("nfl_games", "Game", None),
            ("nfl_games", "Player", None),
            ("nfl_games", "Standing", None),
            ("nfl_games", "Team", None),
        ],
    ),
    (
        "UCL Bets",
        "ucl_bets",
        True,
        [
            ("ucl_betting", "BetSlip", None),
            ("ucl_betting", "FuturesBet", None),
            ("ucl_betting", "FuturesMarket", None),
            ("ucl_betting", "FuturesOutcome", None),
            ("ucl_betting", "Parlay", None),
        ],
    ),
    (
        "UCL Matches",
        "ucl_matches_group",
        True,
        [
            ("ucl_matches", "Match", None),
            ("ucl_matches", "Odds", None),
            ("ucl_matches", "Stage", None),
            ("ucl_matches", "Standing", None),
            ("ucl_matches", "Team", None),
        ],
    ),
    (
        "World Cup Bets",
        "worldcup_bets",
        True,
        [
            ("worldcup_betting", "BetSlip", None),
            ("worldcup_betting", "FuturesBet", None),
            ("worldcup_betting", "FuturesMarket", None),
            ("worldcup_betting", "FuturesOutcome", None),
            ("worldcup_betting", "Parlay", None),
        ],
    ),
    (
        "World Cup Matches",
        "worldcup_matches_group",
        True,
        [
            ("worldcup_matches", "Group", None),
            ("worldcup_matches", "MatchNotes", None),
            ("worldcup_matches", "Match", None),
            ("worldcup_matches", "Odds", None),
            ("worldcup_matches", "Stage", None),
            ("worldcup_matches", "Standing", None),
            ("worldcup_matches", "Team", None),
        ],
    ),
    (
        "Misc",
        "misc",
        False,
        [
            ("betting", "Badge", None),
            ("global_bots", "ScheduleTemplate", None),
            ("hub", "SiteSettings", None),
            ("betting", "UserBadge", None),
            ("betting", "UserBalance", None),
        ],
    ),
]


class VinoAdminSite(AdminSite):
    site_header = "Vinosports Admin"
    site_title = "Vinosports"
    index_title = "Site Administration"

    def get_app_list(self, request, app_label=None):
        default_app_list = super().get_app_list(request, app_label)

        # When viewing a single app's page, return the default
        if app_label:
            return default_app_list

        # Flatten all models into a lookup: (app_label, object_name) -> model_dict
        all_models = {}
        for app in default_app_list:
            for model in app["models"]:
                key = (app["app_label"], model["object_name"])
                all_models[key] = model

        # Build the custom grouped list
        result = []
        used_keys = set()

        for group_name, group_slug, collapsed, model_specs in ADMIN_GROUPS:
            models = []
            for spec in model_specs:
                al, obj_name, display_override = spec
                key = (al, obj_name)
                if key in all_models:
                    model_entry = all_models[key].copy()
                    if display_override:
                        model_entry["name"] = display_override
                    models.append(model_entry)
                    used_keys.add(key)

            if models:
                result.append(
                    {
                        "name": group_name,
                        "app_label": group_slug,
                        "app_url": "",
                        "has_module_perms": True,
                        "models": models,
                        "collapsed": collapsed,
                    }
                )

        # Collect any remaining models not explicitly placed
        remaining = []
        for key, model_entry in all_models.items():
            if key not in used_keys:
                remaining.append(model_entry)

        if remaining:
            remaining.sort(key=lambda m: m["name"])
            result.append(
                {
                    "name": "Other",
                    "app_label": "other",
                    "app_url": "",
                    "has_module_perms": True,
                    "models": remaining,
                    "collapsed": False,
                }
            )

        return result


class VinoAdminConfig(AdminConfig):
    default_site = "config.admin.VinoAdminSite"
