from django.conf import settings


def global_nav(request):
    return {
        "leagues": getattr(settings, "LEAGUE_URLS", {}),
        "hub_url": "/",
        "current_league": getattr(request, "league", None),
    }
