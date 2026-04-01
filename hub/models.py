from django.db import models


class SiteSettings(models.Model):
    max_users = models.PositiveIntegerField(
        default=100,
        help_text="Maximum number of registered users. Set to 0 for unlimited.",
    )
    registration_closed_message = models.CharField(
        max_length=300,
        default="We've hit our user cap for now. Check back later or follow us for updates on when spots open up.",
        help_text="Message shown on the signup page when registration is closed.",
    )
    bot_reply_probability = models.FloatField(
        default=0.7,
        help_text="Probability a bot replies to a human comment (0.0-1.0).",
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def load_for_update(cls):
        """Load with a row-level lock for use inside transaction.atomic()."""
        obj, _ = cls.objects.select_for_update().get_or_create(pk=1)
        return obj
