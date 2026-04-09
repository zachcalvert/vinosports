from django.conf import settings
from django.core.management.base import BaseCommand

from reddit.service import fetch_all_snapshots, fetch_snapshot_for_league


class Command(BaseCommand):
    help = "Fetch hot posts from configured subreddits"

    def add_arguments(self, parser):
        parser.add_argument(
            "--league",
            type=str,
            help="Fetch for a single league (e.g., epl, nba)",
        )

    def handle(self, *args, **options):
        league = options.get("league")
        if league:
            subreddits = getattr(settings, "LEAGUE_SUBREDDITS", {})
            subreddit_name = subreddits.get(league)
            if not subreddit_name:
                self.stderr.write(f"No subreddit configured for league '{league}'")
                return
            snapshot = fetch_snapshot_for_league(league, subreddit_name)
            self.stdout.write(
                f"Fetched r/{subreddit_name}: {snapshot.post_count} posts"
            )
        else:
            count = fetch_all_snapshots()
            self.stdout.write(f"Fetched snapshots for {count} leagues")
