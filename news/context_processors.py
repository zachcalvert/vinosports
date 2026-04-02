from .models import NewsArticle


def latest_articles(request):
    """Inject latest published articles for hub homepage and league dashboards."""
    league = getattr(request, "league", None)
    qs = NewsArticle.objects.filter(
        status=NewsArticle.Status.PUBLISHED,
    ).select_related("author__bot_profile")
    if league:
        qs = qs.filter(league=league)
    return {"latest_articles": qs[:4]}
