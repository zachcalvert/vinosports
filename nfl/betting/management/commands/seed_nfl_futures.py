"""
Management command: seed_nfl_futures

Creates futures markets (Super Bowl, AFC/NFC Champion, Division Winners) for the
current season with outcomes for all teams. Runs the odds engine to generate
initial odds.

Usage:
  python manage.py seed_nfl_futures
  python manage.py seed_nfl_futures --season 2025
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from nfl.betting.futures_odds_engine import CONFERENCE_DIVISIONS, generate_futures_odds
from nfl.betting.models import FuturesMarket, FuturesOutcome
from nfl.games.models import Conference, Division, Standing, Team
from vinosports.betting.models import FuturesMarketStatus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Seed NFL futures markets with outcomes for all teams"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Season to create markets for (default: current season)",
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        season = options["season"] or (
            today.year if today.month >= 9 else today.year - 1
        )
        season_str = str(season)

        teams = list(Team.objects.all())
        if not teams:
            self.stderr.write(self.style.ERROR("No teams found. Run seed_nfl first."))
            return

        self.stdout.write(
            f"Seeding NFL futures for season {season} ({len(teams)} teams)..."
        )

        # Build conference/division team lookups from standings
        standings = list(
            Standing.objects.filter(season=season).values(
                "team_id", "conference", "division"
            )
        )
        conf_team_ids = {Conference.AFC: set(), Conference.NFC: set()}
        div_team_ids = {d: set() for d in Division}
        for s in standings:
            conf = s.get("conference")
            div = s.get("division")
            tid = s.get("team_id")
            if conf in conf_team_ids and tid:
                conf_team_ids[conf].add(tid)
            if div in div_team_ids and tid:
                div_team_ids[div].add(tid)

        # 1. Super Bowl Winner — all 32 teams
        self._seed_market(
            season_str,
            season,
            "SUPER_BOWL",
            f"Super Bowl Winner {season}",
            teams,
            division="",
        )

        # 2. AFC Champion
        afc_teams = [t for t in teams if t.id in conf_team_ids[Conference.AFC]]
        if not afc_teams:
            afc_teams = [t for t in teams if t.conference == Conference.AFC]
        self._seed_market(
            season_str,
            season,
            "AFC_CHAMPION",
            f"AFC Champion {season}",
            afc_teams,
            division="",
        )

        # 3. NFC Champion
        nfc_teams = [t for t in teams if t.id in conf_team_ids[Conference.NFC]]
        if not nfc_teams:
            nfc_teams = [t for t in teams if t.conference == Conference.NFC]
        self._seed_market(
            season_str,
            season,
            "NFC_CHAMPION",
            f"NFC Champion {season}",
            nfc_teams,
            division="",
        )

        # 4. Division Winners — 8 markets of 4 teams each
        for conf, divisions in CONFERENCE_DIVISIONS.items():
            for div in divisions:
                div_teams = [t for t in teams if t.id in div_team_ids.get(div, set())]
                if not div_teams:
                    div_teams = [t for t in teams if t.division == div]
                div_label = Division(div).label
                self._seed_market(
                    season_str,
                    season,
                    "DIVISION",
                    f"{div_label} Winner {season}",
                    div_teams,
                    division=div,
                )

        self.stdout.write(self.style.SUCCESS("NFL futures seeding complete."))

    def _seed_market(self, season_str, season_int, market_type, name, teams, division):
        market, created = FuturesMarket.objects.update_or_create(
            season=season_str,
            market_type=market_type,
            division=division,
            defaults={
                "name": name,
                "status": FuturesMarketStatus.OPEN,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} market: {name}")

        # Generate odds from standings
        kwargs = {"season": season_int, "market_type": market_type}
        if market_type == "DIVISION":
            kwargs["division"] = division
        odds_results = generate_futures_odds(**kwargs)
        odds_map = {r["team_id"]: r["odds"] for r in odds_results}

        now = timezone.now()
        for team in teams:
            odds = odds_map.get(team.pk, 5000)  # fallback long-shot odds

            FuturesOutcome.objects.update_or_create(
                market=market,
                team=team,
                defaults={
                    "odds": odds,
                    "is_active": True,
                    "odds_updated_at": now,
                },
            )

        self.stdout.write(self.style.SUCCESS(f"    {len(teams)} outcomes seeded"))
