from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from games.models import Game

from discussions.forms import CommentForm
from discussions.models import Comment


class CreateCommentView(LoginRequiredMixin, View):
    def post(self, request, id_hash):
        game = get_object_or_404(Game, id_hash=id_hash)
        form = CommentForm(request.POST)

        if not form.is_valid():
            return HttpResponse("Invalid comment", status=400)

        comment = Comment.objects.create(
            user=request.user,
            game=game,
            body=form.cleaned_data["body"],
        )

        if getattr(request, "htmx", False):
            return render(
                request, "discussions/partials/comment.html", {"comment": comment}
            )
        from django.shortcuts import redirect

        return redirect("games:game_detail", id_hash=game.id_hash)


class CreateReplyView(LoginRequiredMixin, View):
    def post(self, request, id_hash, comment_id):
        game = get_object_or_404(Game, id_hash=id_hash)
        parent = get_object_or_404(Comment, pk=comment_id, game=game)
        form = CommentForm(request.POST)

        if not form.is_valid():
            return HttpResponse("Invalid reply", status=400)

        reply = Comment.objects.create(
            user=request.user,
            game=game,
            parent=parent,
            body=form.cleaned_data["body"],
        )

        if getattr(request, "htmx", False):
            return render(
                request, "discussions/partials/comment.html", {"comment": reply}
            )
        from django.shortcuts import redirect

        return redirect("games:game_detail", id_hash=game.id_hash)
