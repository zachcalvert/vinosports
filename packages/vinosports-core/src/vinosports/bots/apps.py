from django.apps import AppConfig


class BotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vinosports.bots"
    label = "global_bots"
    verbose_name = "Bot Profiles"
