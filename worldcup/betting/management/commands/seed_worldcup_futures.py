"""Seed World Cup futures markets — tournament winner, group winners."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create World Cup 2026 futures markets and initial odds"

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh-odds",
            action="store_true",
            help="Recalculate and update odds for all existing open markets (skips market/outcome creation).",
        )

    def handle(self, *args, **options):
        if options["refresh_odds"]:
            from worldcup.betting.futures_odds_engine import update_all_futures_odds

            self.stdout.write("Refreshing odds for all open futures markets...")
            update_all_futures_odds()
            self.stdout.write(self.style.SUCCESS("Futures odds refreshed!"))
            return

        from worldcup.betting.futures_odds_engine import (
            generate_group_winner_odds,
            generate_winner_odds,
        )
        from worldcup.betting.models import FuturesMarket, FuturesOutcome
        from worldcup.matches.models import Group

        season = "2026"

        # Tournament Winner market
        winner_market, created = FuturesMarket.objects.update_or_create(
            season=season,
            market_type=FuturesMarket.MarketType.WINNER,
            group=None,
            defaults={"name": "2026 World Cup Winner"},
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
            group=None,
            defaults={"name": "2026 World Cup Finalist"},
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
                            Decimal("1.05"), (odds / 2).quantize(Decimal("0.01"))
                        )
                    },
                )

        # Group Winner markets (one per group)
        for group in Group.objects.all():
            gw_market, created = FuturesMarket.objects.update_or_create(
                season=season,
                market_type=FuturesMarket.MarketType.GROUP_WINNER,
                group=group,
                defaults={"name": f"Group {group.letter} Winner"},
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created GROUP_WINNER market for Group {group.letter}"
                    )
                )
                odds_map = generate_group_winner_odds(group)
                for team, odds in odds_map.items():
                    FuturesOutcome.objects.get_or_create(
                        market=gw_market,
                        team=team,
                        defaults={"odds": odds},
                    )

        self.stdout.write(self.style.SUCCESS("World Cup futures seed complete!"))
