import random
import string

from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_short_id():
    """Generate a random 8-character alphanumeric string."""
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(8))


class BaseModel(models.Model):
    """Abstract base model with id_hash, created_at, and updated_at."""

    id = models.BigAutoField(primary_key=True)
    id_hash = models.CharField(
        _("ID Hash"),
        max_length=8,
        default=generate_short_id,
        editable=False,
        unique=True,
        help_text=_("Unique 8-character identifier for client-side use"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True
