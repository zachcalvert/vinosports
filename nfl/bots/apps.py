from django.apps import AppConfig


class BotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nfl.bots"
    label = "nfl_bots"
    verbose_name = "NFL Bots"
