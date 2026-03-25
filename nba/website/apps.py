from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nba.website"
    label = "nba_website"
    verbose_name = "Website"
