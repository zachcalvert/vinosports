from django.urls import path

from worldcup.discussions.views import CommentListView

app_name = "worldcup_discussions"

urlpatterns = [
    path(
        "match/<slug:match_slug>/comments/",
        CommentListView.as_view(),
        name="comment_list",
    ),
]
