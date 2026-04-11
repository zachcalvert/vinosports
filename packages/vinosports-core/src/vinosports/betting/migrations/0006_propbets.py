"""Generated migration for PropBet and PropBetSlip models.

Created: 2026-04-11
"""

from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import vinosports.core.models


class Migration(migrations.Migration):

    dependencies = [
        ("betting", "0005_update_featured_parlay_default_stake_10k"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PropBet",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "id_hash",
                    models.CharField(
                        default=vinosports.core.models.generate_short_id,
                        editable=False,
                        help_text="Unique 8-character identifier for client-side use",
                        max_length=8,
                        unique=True,
                        verbose_name="ID Hash",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="updated at")),
                ("title", models.CharField(max_length=200, verbose_name="title")),
                ("description", models.TextField(blank=True, default="", verbose_name="description")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("OPEN", "Open"),
                            ("CLOSED", "Closed"),
                            ("SETTLED", "Settled"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="DRAFT",
                        max_length=10,
                        verbose_name="status",
                    ),
                ),
                ("open_at", models.DateTimeField(blank=True, null=True, verbose_name="open at")),
                ("close_at", models.DateTimeField(blank=True, null=True, verbose_name="close at")),
                ("yes_odds", models.DecimalField(decimal_places=3, max_digits=8, default=Decimal("2.00"), verbose_name="yes odds")),
                ("no_odds", models.DecimalField(decimal_places=3, max_digits=8, default=Decimal("2.00"), verbose_name="no odds")),
                ("total_stake_yes", models.DecimalField(decimal_places=2, max_digits=14, default=Decimal("0"), verbose_name="total stake yes")),
                ("total_stake_no", models.DecimalField(decimal_places=2, max_digits=14, default=Decimal("0"), verbose_name="total stake no")),
                ("settled_outcome", models.BooleanField(blank=True, null=True, verbose_name="settled outcome (True=yes, False=no)")),
                ("settled_at", models.DateTimeField(blank=True, null=True, verbose_name="settled at")),
            ],
            options={
                "ordering": ["-created_at"],
                "permissions": [("settle_propbet", "Can settle prop bet")],
            },
        ),
        migrations.CreateModel(
            name="PropBetSlip",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "id_hash",
                    models.CharField(
                        default=vinosports.core.models.generate_short_id,
                        editable=False,
                        help_text="Unique 8-character identifier for client-side use",
                        max_length=8,
                        unique=True,
                        verbose_name="ID Hash",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="updated at")),
                ("stake", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="stake")),
                (
                    "status",
                    models.CharField(
                        choices=[("PENDING", "Pending"), ("WON", "Won"), ("LOST", "Lost"), ("VOID", "Void")],
                        default="PENDING",
                        max_length=10,
                        verbose_name="status",
                    ),
                ),
                ("payout", models.DecimalField(blank=True, null=True, decimal_places=2, max_digits=14, verbose_name="payout")),
                (
                    "selection",
                    models.CharField(
                        choices=[("YES", "Yes"), ("NO", "No")], max_length=3, verbose_name="selection"
                    ),
                ),
                ("odds", models.DecimalField(decimal_places=3, max_digits=8, verbose_name="odds at placement")),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="betting_bets", to=settings.AUTH_USER_MODEL, verbose_name="user"),
                ),
                (
                    "prop",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bets", to="betting.propbet", verbose_name="prop market"),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="propbet",
            name="creator",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="created_prop_bets", to=settings.AUTH_USER_MODEL, verbose_name="creator"),
        ),
        migrations.AddField(
            model_name="propbet",
            name="settled_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="settled_prop_bets", to=settings.AUTH_USER_MODEL, verbose_name="settled by"),
        ),
    ]
