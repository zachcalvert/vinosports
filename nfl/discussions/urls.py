from django.urls import path

from nfl.discussions.views import CreateCommentView, CreateReplyView, DeleteCommentView

app_name = "nfl_discussions"

urlpatterns = [
    path(
        "game/<str:id_hash>/comments/create/",
        CreateCommentView.as_view(),
        name="create_comment",
    ),
    path(
        "game/<str:id_hash>/comments/<int:comment_id>/reply/",
        CreateReplyView.as_view(),
        name="create_reply",
    ),
    path(
        "game/<str:id_hash>/comments/<int:comment_id>/delete/",
        DeleteCommentView.as_view(),
        name="delete_comment",
    ),
]
