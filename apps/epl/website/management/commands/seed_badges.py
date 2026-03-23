from django.core.management.base import BaseCommand

from betting.badges import BADGE_DEFINITIONS
from vinosports.betting.models import Badge


class Command(BaseCommand):
    help = "Seed Badge rows from BADGE_DEFINITIONS"

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for defn in BADGE_DEFINITIONS:
            slug = defn["slug"]
            _, was_created = Badge.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": defn["name"],
                    "description": defn["description"],
                    "icon": defn["icon"],
                    "rarity": defn["rarity"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"  Badges: {created} created, {updated} updated")
        )
