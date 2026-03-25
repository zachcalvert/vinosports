from django.apps import AppConfig


class NbaBettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nba.betting"
    label = "nba_betting"
    verbose_name = "NBA Betting"

    def ready(self):
        import nba.betting.signals  # noqa: F401
