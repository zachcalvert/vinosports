from .models import SubredditSnapshot


def build_reddit_context(league, max_posts=5):
    """Build a Reddit context string for bot/article prompts.

    Returns an empty string if no recent snapshot exists, so callers can
    safely append this to any prompt without conditional logic.
    """
    snapshot = SubredditSnapshot.objects.filter(league=league).first()
    if not snapshot:
        return ""

    posts = snapshot.data.get("posts", [])[:max_posts]
    if not posts:
        return ""

    lines = [f"Trending on r/{snapshot.subreddit} today:"]
    for post in posts:
        lines.append(f'- "{post["title"]}" ({post["score"]} upvotes)')
        if post.get("top_comments"):
            top = post["top_comments"][0]
            lines.append(f'  Top reply: "{top["body"][:150]}"')
    return "\n".join(lines)
