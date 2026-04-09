"""Management command to generate a league/tournament preview article."""

from django.core.management.base import BaseCommand, CommandError

VALID_LEAGUES = ["epl", "nba", "nfl", "ucl", "worldcup"]


class Command(BaseCommand):
    help = "Generate a league/tournament preview article from futures odds data."

    def add_arguments(self, parser):
        parser.add_argument(
            "league",
            type=str,
            choices=VALID_LEAGUES,
            help="League to preview (epl, nba, nfl, ucl, worldcup)",
        )

    def handle(self, *args, **options):
        from news.article_service import generate_league_preview

        league = options["league"]
        self.stdout.write(f"Generating preview for {league}...")

        article = generate_league_preview(league)

        if article is None:
            raise CommandError(
                f"Preview generation failed for {league}. "
                "Check that open futures markets exist and at least one bot is active."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Preview created (draft): {article.title} [{article.id_hash}]"
            )
        )
