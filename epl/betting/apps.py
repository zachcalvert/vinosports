from django.apps import AppConfig


class EplBettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "epl.betting"
    label = "epl_betting"
    verbose_name = "EPL Betting"

    def ready(self):
        import epl.betting.signals  # noqa: F401
