from django.apps import AppConfig


class DiscussionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nfl.discussions"
    label = "nfl_discussions"
    verbose_name = "NFL Discussions"
