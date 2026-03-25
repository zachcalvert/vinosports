import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.db import close_old_connections
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class LiveUpdatesConsumer(WebsocketConsumer):
    """WebSocket consumer for live game score updates.

    Clients connect via ws/live/<scope>/ where scope is either
    "dashboard" (all matches) or a game id_hash (single game).
    """

    def connect(self):
        self.scope_param = self.scope["url_route"]["kwargs"]["scope"]

        if self.scope_param == "dashboard":
            self.group_name = "live_scores"
        else:
            self.group_name = f"game_{self.scope_param}"

        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def score_update(self, event):
        """Handle dashboard-level score updates."""
        self.send(text_data=event.get("html", ""))

    def game_score_update(self, event):
        """Handle game detail page score updates — render OOB scoreboard + box score."""
        close_old_connections()
        game_pk = event.get("game_pk")
        try:
            from .models import Game, GameStatus, PlayerBoxScore

            game = (
                Game.objects.filter(pk=game_pk)
                .select_related("home_team", "away_team")
                .first()
            )
            if not game:
                return
            html = render_to_string(
                "games/partials/scoreboard_oob.html", {"game": game}
            )

            # Append box score OOB if data exists
            if game.status in (
                GameStatus.IN_PROGRESS,
                GameStatus.HALFTIME,
                GameStatus.FINAL,
            ):
                box_scores = PlayerBoxScore.objects.filter(game=game).select_related(
                    "team"
                )
                if box_scores.exists():
                    away_all = list(box_scores.filter(team=game.away_team))
                    home_all = list(box_scores.filter(team=game.home_team))

                    def _totals(players):
                        t = {
                            "points": 0,
                            "reb": 0,
                            "ast": 0,
                            "stl": 0,
                            "blk": 0,
                            "turnovers": 0,
                            "pf": 0,
                            "fgm": 0,
                            "fga": 0,
                            "fg3m": 0,
                            "fg3a": 0,
                            "ftm": 0,
                            "fta": 0,
                        }
                        for p in players:
                            for k in t:
                                t[k] += getattr(p, k)
                        return t

                    box_ctx = {
                        "game": game,
                        "away_starters": [p for p in away_all if p.starter],
                        "away_bench": [p for p in away_all if not p.starter],
                        "home_starters": [p for p in home_all if p.starter],
                        "home_bench": [p for p in home_all if not p.starter],
                        "away_totals": _totals(away_all),
                        "home_totals": _totals(home_all),
                    }
                    html += render_to_string(
                        "games/partials/box_score_oob.html", box_ctx
                    )

            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering game_score_update for game %s", game_pk)
