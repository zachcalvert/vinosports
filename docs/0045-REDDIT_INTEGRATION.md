# 0045 — Reddit Integration

## Motivation

Bot comments and news articles currently draw context from match data, odds, betting stats, match notes, and global knowledge headlines. Adding real-time subreddit chatter gives bots a richer, more topical voice — they can reference trade rumors, injury news, fan sentiment, and memes that are circulating *today*, not just structured data we already have.

## Concept

Each league gets a `subreddit_url` (e.g., `r/PremierLeague`, `r/nba`). A daily Celery task fetches the hot posts and top comments from each subreddit, stores them, and makes them available as additional context when generating bot comments and articles.

## Reddit API Feasibility

**Status (as of April 2026):** Still viable for this use case.

| Concern | Assessment |
|---------|-----------|
| Free tier | 100 requests/min, OAuth2 required. ~5 subreddits × ~25 posts × ~10 comments = ~55 API calls/day. Well within limits. |
| Auth | Register an OAuth2 "script" app at reddit.com/prefs/apps. Get `client_id` + `client_secret`. App-only (client credentials) OAuth suffices for public data — no user login needed. |
| Library | **PRAW** (Python Reddit API Wrapper) — actively maintained, handles OAuth + rate limiting + pagination. `pip install praw` |
| AI/LLM data policy | Reddit ToS prohibits using content to *train* models. Using it as *real-time context* (RAG-style prompt injection, not fine-tuning) is a gray area. Risk is low for a small hobby project but worth monitoring. We never store Reddit content long-term or use it for training. |

**Env vars needed:** `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`

## Data Model

### Option A: League-level config field (recommended)

Add a `subreddit` CharField to each league's configuration. Since there's no centralized League model, this means adding it to a natural home per league. Two sub-options:

**A1 — New shared model: `core.LeagueConfig`**
```python
class LeagueConfig(BaseModel):
    league = CharField(max_length=20, unique=True)  # "epl", "nba", etc.
    subreddit = CharField(max_length=100)            # "PremierLeague"
    # Future: other league-level settings
```
Pro: Single table, easy to query. Con: New model for one field (for now).

**A2 — Settings dict in `config/settings.py`**
```python
LEAGUE_SUBREDDITS = {
    "epl": "PremierLeague",
    "nba": "nba",
    "nfl": "nfl",
    "worldcup": "worldcup",
    "ucl": "ChampionsLeague",
}
```
Pro: Zero migrations, trivially simple. Con: Not admin-editable.

**Recommendation:** Start with A2 (settings dict). Promote to a model later if we need admin editability or more league-level config fields.

### Reddit content storage

```python
# New app: reddit/ (or add to vinosports-core)
class SubredditSnapshot(BaseModel):
    """Daily snapshot of hot posts + comments for a subreddit."""
    league = CharField(max_length=20, db_index=True)
    subreddit = CharField(max_length=100)
    fetched_at = DateTimeField()
    data = JSONField()  # Structured post + comment data (see below)

    class Meta:
        ordering = ["-fetched_at"]
```

The `data` JSONField holds:
```json
{
  "posts": [
    {
      "id": "abc123",
      "title": "Salah extension confirmed!",
      "score": 4521,
      "num_comments": 312,
      "url": "https://reddit.com/r/...",
      "created_utc": "2026-04-09T14:00:00Z",
      "top_comments": [
        {
          "body": "Finally, my FPL team is saved",
          "score": 891
        }
      ]
    }
  ],
  "fetched_at": "2026-04-09T06:00:00Z",
  "post_count": 25,
  "comment_count": 250
}
```

**Retention:** Keep 7 days of snapshots, auto-purge older ones. We're using this as ephemeral context, not a data warehouse.

## Fetching Logic

### New module: `reddit/service.py`

```python
import praw

MIN_POST_SCORE = 50  # Filter out low-quality posts

def fetch_subreddit_hot(subreddit_name: str, post_limit=25, comment_limit=5) -> dict:
    """Fetch hot posts and top comments from a subreddit. Filters low-quality content."""
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )
    subreddit = reddit.subreddit(subreddit_name)
    posts = []
    for submission in subreddit.hot(limit=post_limit):
        if submission.score < MIN_POST_SCORE:
            continue
        if submission.stickied:
            continue

        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)
        top_comments = [
            {"body": c.body[:200], "score": c.score}
            for c in submission.comments[:comment_limit]
            if not c.stickied and c.score > 10
        ]
        posts.append({
            "id": submission.id,
            "title": submission.title,
            "score": submission.score,
            "num_comments": submission.num_comments,
            "url": submission.url,
            "created_utc": submission.created_utc,
            "selftext": submission.selftext[:500] if submission.is_self else None,
            "is_self": submission.is_self,
            "top_comments": top_comments,
        })
    return {"posts": posts, "post_count": len(posts)}
```

### Celery task: `reddit/tasks.py`

```python
@shared_task(bind=True, max_retries=2)
def fetch_subreddit_snapshots(self):
    """Fetch hot posts for all configured subreddits. Runs twice daily."""
    for league, subreddit in settings.LEAGUE_SUBREDDITS.items():
        data = fetch_subreddit_hot(subreddit)
        SubredditSnapshot.objects.create(
            league=league,
            subreddit=subreddit,
            fetched_at=now(),
            data=data,
        )
```

**Schedule:** Twice daily — 6:00 AM ET and 2:00 PM ET. The morning fetch seeds early bot activity; the afternoon fetch captures gameday chatter before evening matches. Add both to `CELERY_BEAT_SCHEDULE`.

## Context Injection

### For bot comments (`comment_service.py`)

Add a helper that pulls today's snapshot and formats it for the prompt:

```python
def build_reddit_context(league: str, max_posts=5) -> str:
    """Build Reddit context string for bot prompts."""
    snapshot = SubredditSnapshot.objects.filter(
        league=league,
    ).first()  # ordered by -fetched_at, so this is the latest
    if not snapshot:
        return ""

    lines = [f"Trending on r/{snapshot.subreddit} today:"]
    for post in snapshot.data["posts"][:max_posts]:
        lines.append(f"- \"{post['title']}\" ({post['score']} upvotes)")
        if post.get("top_comments"):
            top = post["top_comments"][0]
            lines.append(f"  Top reply: \"{top['body'][:150]}\"")
    return "\n".join(lines)
```

Then inject into `_build_user_prompt()` alongside existing context (match data, odds, bot stats, global knowledge). The key principle: **Reddit context is additive, not replacing anything.** Bots can reference it or ignore it — the Claude prompt already handles variable context gracefully.

### For articles (`article_service.py`)

Same pattern — inject `build_reddit_context()` into recap/roundup/trend prompt builders. Articles can reference "fan sentiment on social media" without citing Reddit directly.

## Implementation Plan

### Phase 1: Plumbing (small, shippable)
1. Add `LEAGUE_SUBREDDITS` dict to settings
2. Create `reddit/` Django app with `SubredditSnapshot` model
3. Implement `reddit/service.py` (PRAW fetch logic)
4. Implement `reddit/tasks.py` (daily fetch task)
5. Add to `CELERY_BEAT_SCHEDULE`
6. Add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` to env
7. Add `praw` to dependencies
8. Migration + test that fetch works against a real subreddit

### Phase 2: Context injection
9. Add `build_reddit_context()` helper
10. Inject into EPL `comment_service.py` `_build_user_prompt()` (start with one league)
11. Inject into `article_service.py` recap prompts (EPL first)
12. Verify bot output references trending topics naturally
13. Roll out to NBA, NFL, World Cup, UCL

### Phase 3: Polish
14. Admin visibility — show today's snapshot in Django admin (readonly JSONField)
15. Management command for manual fetch (`python manage.py fetch_reddit`)
16. 7-day retention cleanup task
17. Graceful degradation — if Reddit fetch fails, bots still work (just without Reddit context)

## Subreddit Candidates

| League | Subreddit | Subscribers (approx) | Notes |
|--------|-----------|---------------------|-------|
| EPL | r/PremierLeague | ~1.5M | Main EPL sub |
| NBA | r/nba | ~12M | Extremely active, great for hot takes |
| NFL | r/nfl | ~10M | Active, especially during season |
| World Cup | r/worldcup | ~500K | Active during tournaments |
| UCL | r/ChampionsLeague | ~200K | Smaller but focused |

## Decisions

1. **Two fetches per day** — morning (~6am ET) and afternoon (~2pm ET). The second fetch captures gameday chatter before evening matches/games ramp up.
2. **Aggressive comment truncation** — 200 chars max per comment. Bot comments on the site should be short (two sentences max); long-form lives in articles. Reddit context should match that brevity.
3. **Filter low-quality posts** — Prioritize text/self posts. Filter out posts below a score threshold (e.g., <50 upvotes). Memes and link-only posts are noise.
4. **One subreddit per league** to start. Expand later if valuable.
5. **Separate from GlobalKnowledge** — Reddit snapshots stay in their own model. GlobalKnowledge remains manually curated.