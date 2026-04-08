"""Seed UCL futures markets — tournament winner, finalist, top 8."""

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create UCL futures markets and initial odds"

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh-odds",
            action="store_true",
            help="Recalculate and update odds for all existing open markets (skips market/outcome creation).",
        )

    def handle(self, *args, **options):
        if options["refresh_odds"]:
            from ucl.betting.futures_odds_engine import update_all_futures_odds

            self.stdout.write("Refreshing odds for all open futures markets...")
            update_all_futures_odds()
            self.stdout.write(self.style.SUCCESS("UCL futures odds refreshed!"))
            return

        from ucl.betting.futures_odds_engine import (
            generate_top_8_odds,
            generate_winner_odds,
        )
        from ucl.betting.models import FuturesMarket, FuturesOutcome

        season = getattr(settings, "UCL_CURRENT_SEASON", "2025")

        # Tournament Winner market
        winner_market, created = FuturesMarket.objects.update_or_create(
            season=season,
            market_type=FuturesMarket.MarketType.WINNER,
            defaults={"name": f"{season}-{int(season) + 1} UCL Winner"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created WINNER market"))
            odds_map = generate_winner_odds()
            for team, odds in odds_map.items():
                FuturesOutcome.objects.get_or_create(
                    market=winner_market,
                    team=team,
                    defaults={"odds": odds},
                )

        # Finalist market
        finalist_market, created = FuturesMarket.objects.update_or_create(
            season=season,
            market_type=FuturesMarket.MarketType.FINALIST,
            defaults={"name": f"{season}-{int(season) + 1} UCL Finalist"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created FINALIST market"))
            odds_map = generate_winner_odds()
            from decimal import Decimal

            for team, odds in odds_map.items():
                FuturesOutcome.objects.get_or_create(
                    market=finalist_market,
                    team=team,
                    defaults={
                        "odds": max(
                            Decimal("1.05"),
                            (odds / Decimal("1.8")).quantize(Decimal("0.01")),
                        )
                    },
                )

        # Top 8 market
        top8_market, created = FuturesMarket.objects.update_or_create(
            season=season,
            market_type=FuturesMarket.MarketType.TOP_8,
            defaults={"name": f"{season}-{int(season) + 1} UCL League Phase Top 8"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created TOP_8 market"))
            odds_map = generate_top_8_odds()
            for team, odds in odds_map.items():
                FuturesOutcome.objects.get_or_create(
                    market=top8_market,
                    team=team,
                    defaults={"odds": odds},
                )

        self.stdout.write(self.style.SUCCESS("UCL futures seed complete!"))
