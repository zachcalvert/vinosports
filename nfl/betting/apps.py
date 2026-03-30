from django.apps import AppConfig


class BettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nfl.betting"
    label = "nfl_betting"
    verbose_name = "NFL Betting"
