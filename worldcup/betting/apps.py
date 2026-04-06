from django.apps import AppConfig


class BettingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "worldcup.betting"
    label = "worldcup_betting"
    verbose_name = "World Cup Betting"
