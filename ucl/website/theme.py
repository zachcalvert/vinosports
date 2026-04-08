THEME_COOKIE = "ucl_theme"


def get_theme(request):
    return request.COOKIES.get(THEME_COOKIE, "dark")
