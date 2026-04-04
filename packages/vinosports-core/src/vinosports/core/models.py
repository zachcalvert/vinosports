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


class GlobalKnowledge(BaseModel):
    """Curated real-world headlines injected into all bot prompts at runtime."""

    headline = models.CharField(
        max_length=200,
        help_text="Short headline (e.g. 'Messi rejoins Barcelona for a farewell tour')",
    )
    detail = models.TextField(
        blank=True,
        help_text="Optional expanded context — only include if bots need more than the headline",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Lower numbers appear first. Keep 3-5 active at a time.",
    )

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Global Knowledge"
        verbose_name_plural = "Global Knowledge"

    def __str__(self):
        return self.headline
