from django.urls import path

from . import views

app_name = "reactions"

urlpatterns = [
    path(
        "comment/<int:content_type_id>/<int:object_id>/<str:reaction_type>/",
        views.toggle_comment_reaction,
        name="toggle_comment",
    ),
    path(
        "article/<str:id_hash>/<str:reaction_type>/",
        views.toggle_article_reaction,
        name="toggle_article",
    ),
]
