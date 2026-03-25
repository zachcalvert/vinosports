from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from nba.discussions.forms import CommentForm
from nba.discussions.models import Comment
from nba.games.models import Game


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
                request, "nba_discussions/partials/comment.html", {"comment": comment}
            )
        from django.shortcuts import redirect

        return redirect("nba_games:game_detail", id_hash=game.id_hash)


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
                request, "nba_discussions/partials/comment.html", {"comment": reply}
            )
        from django.shortcuts import redirect

        return redirect("nba_games:game_detail", id_hash=game.id_hash)
