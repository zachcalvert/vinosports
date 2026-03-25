"""EPL seed_bots — DEPRECATED.

Bot profiles are now global. Use the hub seed_bots command instead:
    docker compose exec hub-web python manage.py seed_bots
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "DEPRECATED — bot profiles are now global. Use hub seed_bots instead."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "EPL seed_bots is deprecated. "
                "Bot profiles are now global — run seed_bots from the hub service:\n"
                "  docker compose exec hub-web python manage.py seed_bots"
            )
        )
