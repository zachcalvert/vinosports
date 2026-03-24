from django.conf import settings


def global_nav(request):
    return {
        "leagues": getattr(settings, "LEAGUE_URLS", {}),
        "hub_url": getattr(settings, "HUB_URL", "http://localhost:7999"),
        "current_league": getattr(settings, "CURRENT_LEAGUE", None),
    }
