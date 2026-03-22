from django.apps import AppConfig


class NbaBotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bots"
    label = "nba_bots"
    verbose_name = "NBA Bots"
