THEME_SESSION_KEY = "theme_preference"
DEFAULT_THEME = "light"
VALID_THEMES = {"dark", "light"}


def normalize_theme(theme):
    if theme in VALID_THEMES:
        return theme
    return DEFAULT_THEME


def get_theme(request):
    return normalize_theme(request.session.get(THEME_SESSION_KEY, DEFAULT_THEME))


def get_toggle_theme(request):
    current_theme = get_theme(request)
    return "light" if current_theme == "dark" else "dark"
