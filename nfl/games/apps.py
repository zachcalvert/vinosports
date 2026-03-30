from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nfl.games"
    label = "nfl_games"
    verbose_name = "NFL Games"
