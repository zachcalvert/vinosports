from .constants import LEAGUE_NEWS_NAMESPACES
from .models import NewsArticle


def latest_articles(request):
    """Inject latest published articles for hub homepage and league dashboards."""
    league = getattr(request, "league", None)
    qs = NewsArticle.objects.filter(
        status=NewsArticle.Status.PUBLISHED,
    ).select_related("author__bot_profile")
    if league:
        qs = qs.filter(league=league)
    ns = LEAGUE_NEWS_NAMESPACES.get(league, "news")
    latest_previews = (
        list(qs.filter(article_type=NewsArticle.ArticleType.PREVIEW)[:2])
        if league
        else []
    )
    return {
        "latest_articles": qs[:4],
        "latest_previews": latest_previews,
        "news_list_url_name": f"{ns}:article_list",
        "news_detail_url_name": f"{ns}:article_detail",
        "news_delete_url_name": f"{ns}:article_delete",
    }
