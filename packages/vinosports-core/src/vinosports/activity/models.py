from django.db import models
from django.utils.translation import gettext_lazy as _


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
