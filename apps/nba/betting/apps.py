from django.apps import AppConfig


class NbaBettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "betting"
    label = "nba_betting"
    verbose_name = "NBA Betting"
