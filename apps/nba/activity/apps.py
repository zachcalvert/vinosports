from django.apps import AppConfig


class NbaActivityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "activity"
    label = "nba_activity"
    verbose_name = "NBA Activity"
