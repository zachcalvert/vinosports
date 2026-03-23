from django.urls import path

from discussions.views import CreateCommentView, CreateReplyView

app_name = "discussions"

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
]
