import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.db import close_old_connections
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class LiveUpdatesConsumer(WebsocketConsumer):
    """WebSocket consumer for live match score updates.

    Clients connect via ws/live/<scope>/ where scope is either
    "dashboard" (all matches) or a match id_hash (single match).
    """

    def connect(self):
        self.scope_param = self.scope["url_route"]["kwargs"]["scope"]

        if self.scope_param == "dashboard":
            self.group_name = "live_scores"
        else:
            self.group_name = f"match_{self.scope_param}"

        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def score_update(self, event):
        """Handle score_update events broadcast from Celery tasks."""
        close_old_connections()
        match_id = event.get("match_id")
        try:
            from .models import Match

            match = (
                Match.objects.filter(pk=match_id)
                .select_related("home_team", "away_team")
                .first()
            )
            if not match:
                return
            html = render_to_string(
                "matches/partials/match_card_oob.html", {"match": match}
            )
            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering score_update for match %s", match_id)

    def match_score_update(self, event):
        """Handle match detail page score updates."""
        close_old_connections()
        match_id = event.get("match_id")
        try:
            from .models import Match

            match = (
                Match.objects.filter(pk=match_id)
                .select_related("home_team", "away_team")
                .first()
            )
            if not match:
                return
            html = render_to_string(
                "matches/partials/score_display_oob.html", {"match": match}
            )
            self.send(text_data=html)
        except Exception:
            logger.exception(
                "Error rendering match_score_update for match %s", match_id
            )
