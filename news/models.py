from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class NewsArticle(BaseModel):
    """Auto-generated news article written by a bot personality."""

    class ArticleType(models.TextChoices):
        RECAP = "recap", _("Game Recap")
        ROUNDUP = "roundup", _("Weekly Roundup")
        TREND = "trend", _("Betting Trend")
        CROSS_LEAGUE = "cross_league", _("Cross-League")
        PREVIEW = "preview", _("League Preview")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    # Scope
    league = models.CharField(
        _("league"),
        max_length=10,
        blank=True,
        db_index=True,
        help_text=_(
            "'epl', 'nba', 'nfl', 'ucl', 'worldcup', or blank for cross-league"
        ),
    )

    # Author — the bot's User account (same pattern as BotComment.user)
    author = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("author"),
    )

    # Content
    article_type = models.CharField(
        _("article type"), max_length=20, choices=ArticleType.choices
    )
    title = models.CharField(_("title"), max_length=200)
    subtitle = models.CharField(_("subtitle"), max_length=300, blank=True)
    body = models.TextField(_("body"))
    hero_emoji = models.CharField(
        _("hero emoji"),
        max_length=10,
        blank=True,
        help_text=_("Emoji for article card display"),
    )

    # Game reference (recaps only) — denormalized to avoid cross-app FKs
    game_id_hash = models.CharField(
        _("game ID hash"), max_length=12, blank=True, db_index=True
    )
    game_url = models.CharField(_("game URL"), max_length=200, blank=True)
    game_summary = models.CharField(
        _("game summary"),
        max_length=200,
        blank=True,
        help_text=_('e.g. "Lakers 112 - Celtics 108"'),
    )

    # Publishing
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)

    # Generation metadata (same pattern as BotComment.prompt_used / raw_response)
    prompt_used = models.TextField(_("prompt used"), blank=True)
    raw_response = models.TextField(_("raw response"), blank=True)

    class Meta:
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["league", "status", "-published_at"]),
            models.Index(fields=["article_type", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["league", "game_id_hash"],
                condition=models.Q(article_type="recap", game_id_hash__gt=""),
                name="unique_recap_per_game",
            ),
        ]
        verbose_name = _("news article")
        verbose_name_plural = _("news articles")

    def __str__(self):
        return self.title

    def publish(self):
        """Transition article from draft to published."""
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at"])

        from vinosports.reactions.dispatch import dispatch_article_reactions

        dispatch_article_reactions(self)
