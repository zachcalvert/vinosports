from django.views.generic import DetailView, ListView

from .constants import LEAGUE_BASE_TEMPLATES, LEAGUE_NEWS_NAMESPACES
from .models import NewsArticle


class LeagueNewsMixin:
    """Detect league from URL middleware and set base template accordingly."""

    def get_league(self):
        return getattr(self.request, "league", None)

    def get_base_template(self):
        league = self.get_league()
        return LEAGUE_BASE_TEMPLATES.get(league, "hub/base.html")

    def get_news_namespace(self):
        league = self.get_league()
        return LEAGUE_NEWS_NAMESPACES.get(league, "news")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ns = self.get_news_namespace()
        ctx["base_template"] = self.get_base_template()
        ctx["news_namespace"] = ns
        ctx["news_list_url_name"] = f"{ns}:article_list"
        ctx["news_detail_url_name"] = f"{ns}:article_detail"
        return ctx


class ArticleListView(LeagueNewsMixin, ListView):
    model = NewsArticle
    template_name = "news/article_list.html"
    context_object_name = "articles"
    paginate_by = 12

    def get_queryset(self):
        qs = NewsArticle.objects.filter(
            status=NewsArticle.Status.PUBLISHED,
        ).select_related("author__bot_profile")
        # Prefer league from URL middleware, fall back to query param
        league = self.get_league() or self.request.GET.get("league")
        if league in ("epl", "nba", "nfl"):
            qs = qs.filter(league=league)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        league = self.get_league() or self.request.GET.get("league", "")
        ctx["current_league"] = league if league in ("epl", "nba", "nfl") else ""
        ctx["league_choices"] = [("epl", "EPL"), ("nba", "NBA"), ("nfl", "NFL")]
        return ctx

    def get_template_names(self):
        # Return partial only for targeted HTMX swaps (filter tabs),
        # not for hx-boost navigation which needs the full page.
        if self.request.htmx and not self.request.htmx.boosted:
            return ["news/partials/article_feed.html"]
        return [self.template_name]


class ArticleDetailView(LeagueNewsMixin, DetailView):
    model = NewsArticle
    template_name = "news/article_detail.html"
    context_object_name = "article"
    slug_field = "id_hash"
    slug_url_kwarg = "id_hash"

    def get_queryset(self):
        qs = NewsArticle.objects.select_related("author__bot_profile")
        if not self.request.user.is_superuser:
            qs = qs.filter(status=NewsArticle.Status.PUBLISHED)
        return qs
