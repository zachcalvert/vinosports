from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.text import slugify

from vinosports.core.models import generate_short_id

from .managers import UserManager


class Currency(models.TextChoices):
    USD = "USD", "US Dollars ($)"
    GBP = "GBP", "UK Pounds (£)"
    EUR = "EUR", "Euros (€)"


class User(AbstractUser):
    username = None
    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=50, null=True, blank=True)
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.USD,
    )
    is_bot = models.BooleanField(
        default=False,
        help_text="Designates bot/automated accounts.",
    )
    created_by = models.OneToOneField(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bot_user",
        help_text="The real user who created this bot account.",
    )
    avatar_icon = models.CharField(max_length=50, default="user-circle")
    avatar_bg = models.CharField(max_length=7, default="#374151")
    avatar_frame = models.CharField(max_length=50, blank=True, default="")
    avatar_crest_url = models.URLField(blank=True, default="")
    profile_image = models.ImageField(
        upload_to="profile_images/",
        blank=True,
        default="",
        help_text="Profile photo. Used as avatar when set.",
    )
    show_activity_toasts = models.BooleanField(
        default=True,
        help_text="Show live activity feed toasts on every page.",
    )
    promo_code = models.CharField(max_length=100, blank=True, default="")
    id_hash = models.CharField(
        max_length=8,
        default=generate_short_id,
        editable=False,
        unique=True,
    )
    slug = models.SlugField(max_length=70, unique=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("display_name"),
                condition=Q(display_name__isnull=False) & ~Q(display_name=""),
                name="users_user_display_name_unique_non_empty_ci",
            )
        ]

    def __str__(self):
        return self.email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_display_name = self.display_name

    def generate_slug(self):
        name_part = slugify(self.display_name or self.email.split("@")[0])
        max_name = 70 - len(self.id_hash) - 1
        name_part = name_part[:max_name]
        return f"{name_part}-{self.id_hash}"

    def save(self, *args, **kwargs):
        if not self.id_hash:
            self.id_hash = generate_short_id()
        if not self.slug or self.display_name != self._original_display_name:
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)
        self._original_display_name = self.display_name
