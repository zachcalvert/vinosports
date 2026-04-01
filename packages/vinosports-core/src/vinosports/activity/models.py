from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class Notification(BaseModel):
    """Persistent user notification."""

    class Category(models.TextChoices):
        REPLY = "REPLY", "Reply"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True, default="")
    url = models.CharField(max_length=300, blank=True, default="")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        help_text="Unread notifications auto-dismiss after this time."
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_sent",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.category} → {self.recipient} ({self.id_hash})"


class AbstractActivityEvent(models.Model):
    """Abstract activity event for the real-time feed.

    League projects must define their own EventType choices.
    Does not inherit BaseModel — uses its own timestamp fields.
    """

    event_type = models.CharField(_("event type"), max_length=20)
    message = models.CharField(_("message"), max_length=280)
    url = models.CharField(_("url"), max_length=200, blank=True, default="")
    icon = models.CharField(_("icon"), max_length=50, default="lightning")
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    broadcast_at = models.DateTimeField(_("broadcast at"), null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["created_at"]
