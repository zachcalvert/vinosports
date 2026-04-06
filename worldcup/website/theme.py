THEME_COOKIE = "wc_theme"


def get_theme(request):
    return request.COOKIES.get(THEME_COOKIE, "dark")
