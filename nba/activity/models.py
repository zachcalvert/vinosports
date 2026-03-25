from django.db import models

from vinosports.activity.models import AbstractActivityEvent


class ActivityEvent(AbstractActivityEvent):
    """NBA-specific activity events."""

    class EventType(models.TextChoices):
        BOT_BET = "bot_bet", "Bot Bet"
        BOT_COMMENT = "bot_comment", "Bot Comment"
        SCORE_CHANGE = "score_change", "Score Change"
        ODDS_UPDATE = "odds_update", "Odds Update"
        BET_SETTLEMENT = "bet_settlement", "Bet Settlement"
        USER_BET = "user_bet", "User Bet"
        BANKRUPTCY = "bankruptcy", "Bankruptcy"
        BAILOUT = "bailout", "Bailout"

    event_type = models.CharField(max_length=20, choices=EventType.choices)

    class Meta(AbstractActivityEvent.Meta):
        indexes = [
            models.Index(
                fields=["broadcast_at", "created_at"],
                name="nba_act_pending_bcast_idx",
            ),
        ]

    def __str__(self):
        status = "sent" if self.broadcast_at else "queued"
        return f"[{status}] {self.message}"
