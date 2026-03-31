from nfl.website.theme import get_theme


def theme(request):
    if getattr(request, "league", None) != "nfl":
        return {}
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
