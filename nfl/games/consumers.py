import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.db import close_old_connections
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class LiveUpdatesConsumer(WebsocketConsumer):
    """WebSocket consumer for live NFL game score updates.

    Clients connect via ws/live/<scope>/ where scope is either
    "dashboard" (all games) or a game id_hash (single game detail).
    """

    def connect(self):
        self.scope_param = self.scope["url_route"]["kwargs"]["scope"]

        if self.scope_param == "dashboard":
            self.group_name = "nfl_live_scores"
        else:
            self.group_name = f"nfl_game_{self.scope_param}"

        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def score_update(self, event):
        """Handle dashboard-level score updates — render OOB game card."""
        close_old_connections()
        game_pk = event.get("game_pk")
        try:
            from django.db.models import Count

            from .models import Game, Standing

            game = (
                Game.objects.filter(pk=game_pk)
                .select_related("home_team", "away_team")
                .annotate(
                    bet_count=Count("bets", distinct=True),
                    comment_count=Count("comments", distinct=True),
                )
                .first()
            )
            if not game:
                return

            standings_qs = Standing.objects.filter(
                team_id__in=[game.home_team_id, game.away_team_id],
                season=game.season,
            ).select_related("team")
            standings_by_team = {s.team_id: s for s in standings_qs}

            html = render_to_string(
                "nfl_games/partials/game_card_oob.html",
                {"game": game, "standings_by_team": standings_by_team},
            )
            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering score_update for game %s", game_pk)

    def game_score_update(self, event):
        """Handle game detail page score updates — render OOB scoreboard."""
        close_old_connections()
        game_pk = event.get("game_pk")
        try:
            from .models import Game

            game = (
                Game.objects.filter(pk=game_pk)
                .select_related("home_team", "away_team")
                .first()
            )
            if not game:
                return

            html = render_to_string(
                "nfl_games/partials/scoreboard_oob.html", {"game": game}
            )
            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering game_score_update for game %s", game_pk)
