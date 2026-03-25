from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "epl.website"
    label = "epl_website"
    verbose_name = "Website"
