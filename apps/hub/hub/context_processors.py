from django.conf import settings


def league_urls(request):
    return {
        "leagues": settings.LEAGUE_URLS,
        "hub_url": settings.HUB_URL,
    }
