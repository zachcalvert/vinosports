from django.apps import AppConfig


class NbaBettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nba.betting"
    label = "nba_betting"
    verbose_name = "NBA Betting"

    def ready(self):
        import nba.betting.signals  # noqa: F401
        from nba.betting.parlay_adapter import NBAParlayAdapter
        from vinosports.betting.parlay_builder import register_adapter

        register_adapter("nba", NBAParlayAdapter)
