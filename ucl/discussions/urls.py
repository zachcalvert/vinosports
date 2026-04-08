from django.urls import path

from ucl.discussions.views import (
    CommentListView,
    CreateCommentView,
    CreateReplyView,
    DeleteCommentView,
)

app_name = "ucl_discussions"

urlpatterns = [
    path(
        "match/<slug:match_slug>/comments/",
        CommentListView.as_view(),
        name="comment_list",
    ),
    path(
        "match/<slug:match_slug>/comments/create/",
        CreateCommentView.as_view(),
        name="create_comment",
    ),
    path(
        "match/<slug:match_slug>/comments/<int:comment_pk>/reply/",
        CreateReplyView.as_view(),
        name="create_reply",
    ),
    path(
        "match/<slug:match_slug>/comments/<int:comment_pk>/delete/",
        DeleteCommentView.as_view(),
        name="delete_comment",
    ),
]
