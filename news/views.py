from django.views.generic import DetailView, ListView

from .models import NewsArticle


class ArticleListView(ListView):
    model = NewsArticle
    template_name = "news/article_list.html"
    context_object_name = "articles"
    paginate_by = 12

    def get_queryset(self):
        qs = NewsArticle.objects.filter(
            status=NewsArticle.Status.PUBLISHED,
        ).select_related("author__bot_profile")
        league = self.request.GET.get("league")
        if league in ("epl", "nba", "nfl"):
            qs = qs.filter(league=league)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        league = self.request.GET.get("league", "")
        ctx["current_league"] = league if league in ("epl", "nba", "nfl") else ""
        ctx["league_choices"] = [("epl", "EPL"), ("nba", "NBA"), ("nfl", "NFL")]
        return ctx

    def get_template_names(self):
        if self.request.htmx:
            return ["news/partials/article_feed.html"]
        return [self.template_name]


class ArticleDetailView(DetailView):
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
