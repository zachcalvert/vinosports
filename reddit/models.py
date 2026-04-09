from django.db import models

from vinosports.core.models import BaseModel


class SubredditSnapshot(BaseModel):
    """Point-in-time snapshot of hot posts and top comments from a subreddit."""

    league = models.CharField(max_length=20, db_index=True)
    subreddit = models.CharField(max_length=100)
    fetched_at = models.DateTimeField()
    data = models.JSONField(
        help_text="Structured post + comment data from the subreddit's hot feed"
    )

    class Meta:
        ordering = ["-fetched_at"]
        verbose_name = "Subreddit Snapshot"
        verbose_name_plural = "Subreddit Snapshots"

    def __str__(self):
        return f"r/{self.subreddit} — {self.fetched_at:%Y-%m-%d %H:%M}"

    @property
    def post_count(self):
        return self.data.get("post_count", 0) if self.data else 0
