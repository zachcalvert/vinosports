from django.conf import settings as django_settings

from website.theme import get_theme


def hub_url(request):
    return {"hub_url": getattr(django_settings, "HUB_URL", "http://localhost:7999")}


def theme(request):
    current_theme = get_theme(request)
    toggle_theme = "light" if current_theme == "dark" else "dark"

    return {
        "ui_theme_name": current_theme,
        "ui_theme_is_light": current_theme == "light",
        "ui_theme_is_dark": current_theme == "dark",
        "ui_theme_toggle_value": toggle_theme,
        "ui_theme_toggle_label": (
            "Light mode" if toggle_theme == "light" else "Dark mode"
        ),
    }
