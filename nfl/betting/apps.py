from django.apps import AppConfig


class BettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nfl.betting"
    label = "nfl_betting"
    verbose_name = "NFL Betting"

    def ready(self):
        import nfl.betting.signals  # noqa: F401
        from nfl.betting.parlay_adapter import NFLParlayAdapter
        from vinosports.betting.parlay_builder import register_adapter

        register_adapter("nfl", NFLParlayAdapter)

        from nfl.betting.models import BetSlip, Parlay
        from vinosports.challenges.engine import register_league_models

        register_league_models("nfl", BetSlip, Parlay, event_fk_field="game")
