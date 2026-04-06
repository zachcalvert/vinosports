from django.views.generic import ListView

from worldcup.discussions.models import Comment


class CommentListView(ListView):
    model = Comment
    template_name = "worldcup_discussions/partials/comment_list.html"
    context_object_name = "comments"
    paginate_by = 20

    def get_queryset(self):
        return (
            Comment.objects.filter(
                match__slug=self.kwargs["match_slug"],
                parent__isnull=True,
                is_deleted=False,
            )
            .select_related("user")
            .prefetch_related("replies__user")
            .order_by("-created_at")
        )
