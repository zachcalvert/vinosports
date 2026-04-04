from django.urls import path

from . import views

app_name = "news"

urlpatterns = [
    path("", views.ArticleListView.as_view(), name="article_list"),
    path("<str:id_hash>/", views.ArticleDetailView.as_view(), name="article_detail"),
    path(
        "<str:id_hash>/delete/",
        views.ArticleDeleteView.as_view(),
        name="article_delete",
    ),
]
