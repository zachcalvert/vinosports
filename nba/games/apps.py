from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nba.games"
    label = "nba_games"
    verbose_name = "Games"
