from django.conf import settings


def league_urls(request):
    return {
        "leagues": getattr(settings, "LEAGUE_URLS", {}),
        "hub_url": "/",
    }
