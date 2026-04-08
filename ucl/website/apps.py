from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ucl.website"
    label = "ucl_website"
    verbose_name = "UCL Website"
