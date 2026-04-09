import logging

import praw
from django.conf import settings
from django.utils.timezone import now

from .models import SubredditSnapshot

logger = logging.getLogger(__name__)

MIN_POST_SCORE = 50
MIN_COMMENT_SCORE = 10
POST_LIMIT = 25
COMMENT_LIMIT = 5
MAX_SELFTEXT_LENGTH = 500
MAX_COMMENT_LENGTH = 200


def _get_reddit_client():
    """Create and return a Reddit client using app-only (read-only) auth."""
    return praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )


def fetch_subreddit_hot(subreddit_name):
    """Fetch hot posts and top comments from a subreddit, filtering low-quality content.

    Returns a dict with posts and metadata, ready to store in SubredditSnapshot.data.
    """
    reddit = _get_reddit_client()
    subreddit = reddit.subreddit(subreddit_name)

    posts = []
    for submission in subreddit.hot(limit=POST_LIMIT):
        if submission.score < MIN_POST_SCORE:
            continue
        if submission.stickied:
            continue

        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)
        top_comments = [
            {"body": c.body[:MAX_COMMENT_LENGTH], "score": c.score}
            for c in submission.comments[:COMMENT_LIMIT]
            if not c.stickied and c.score >= MIN_COMMENT_SCORE
        ]

        posts.append(
            {
                "id": submission.id,
                "title": submission.title,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "url": submission.url,
                "created_utc": submission.created_utc,
                "selftext": (
                    submission.selftext[:MAX_SELFTEXT_LENGTH]
                    if submission.is_self
                    else None
                ),
                "is_self": submission.is_self,
                "top_comments": top_comments,
            }
        )

    return {"posts": posts, "post_count": len(posts)}


def fetch_snapshot_for_league(league, subreddit_name):
    """Fetch and store a snapshot for a single league. Returns the created snapshot."""
    logger.info("Fetching r/%s for %s", subreddit_name, league)
    data = fetch_subreddit_hot(subreddit_name)
    snapshot = SubredditSnapshot.objects.create(
        league=league,
        subreddit=subreddit_name,
        fetched_at=now(),
        data=data,
    )
    logger.info(
        "Stored snapshot for r/%s: %d posts", subreddit_name, data["post_count"]
    )
    return snapshot


def fetch_all_snapshots():
    """Fetch snapshots for all configured leagues. Returns count of snapshots created."""
    subreddits = getattr(settings, "LEAGUE_SUBREDDITS", {})
    if not subreddits:
        logger.warning("LEAGUE_SUBREDDITS is empty, nothing to fetch")
        return 0

    count = 0
    for league, subreddit_name in subreddits.items():
        try:
            fetch_snapshot_for_league(league, subreddit_name)
            count += 1
        except Exception:
            logger.exception("Failed to fetch r/%s for %s", subreddit_name, league)
    return count


def purge_old_snapshots(days=7):
    """Delete snapshots older than the given number of days."""
    from datetime import timedelta

    cutoff = now() - timedelta(days=days)
    deleted, _ = SubredditSnapshot.objects.filter(fetched_at__lt=cutoff).delete()
    if deleted:
        logger.info("Purged %d old snapshots (older than %d days)", deleted, days)
    return deleted
