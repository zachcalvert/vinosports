from django.apps import AppConfig


class MatchesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "worldcup.matches"
    label = "worldcup_matches"
    verbose_name = "World Cup Matches"
