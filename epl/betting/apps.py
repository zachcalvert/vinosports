from django.apps import AppConfig


class EplBettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "epl.betting"
    label = "epl_betting"
    verbose_name = "EPL Betting"

    def ready(self):
        import epl.betting.signals  # noqa: F401
        from epl.betting.parlay_adapter import EPLParlayAdapter
        from vinosports.betting.parlay_builder import register_adapter

        register_adapter("epl", EPLParlayAdapter)

        from epl.betting.models import BetSlip, Parlay
        from vinosports.challenges.engine import register_league_models

        register_league_models("epl", BetSlip, Parlay, event_fk_field="match")
