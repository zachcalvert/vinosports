from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "worldcup.website"
    label = "worldcup_website"
    verbose_name = "World Cup Website"
