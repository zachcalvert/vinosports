from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nfl.website"
    label = "nfl_website"
    verbose_name = "NFL Website"
