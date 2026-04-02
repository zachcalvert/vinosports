# News System

> Status: **Ready to implement**
> Depends on: Game Notes (0040) ✅

## Vision

Auto-generated news articles powered by game data, betting outcomes, and admin-authored game notes. Bots already react to games in comment threads — this extends them into standalone content creators, producing articles that feel like sports journalism written by opinionated personalities.

## Why This Is Interesting

- **Game notes double-dip**: The same notes Zach writes while watching a game feed both the post-game comment thread AND news articles. One input, two outputs.
- **Builds on what exists**: Bot personalities, Claude API integration, Celery tasks, game result data — all already in place.
- **Content without content creation**: The system generates a feed of articles from data that's already flowing through the platform. No editorial team needed.

## Decisions

### Where do articles live?

**Single `news` app at the repo root.** One concrete `NewsArticle` model handles all leagues and cross-league content.

Why not per-league apps (like betting)? Per-league apps exist because each league has genuinely different fields — EPL uses decimal odds and 1X2 markets, NBA/NFL use American odds and spread/total markets. NewsArticle is structurally identical across leagues. The only league-specific thing is which game it references, and we handle that with denormalized fields (see data model below) rather than cross-app ForeignKeys.

This follows the same pragmatic approach as `BotProfile`, which lives in one place with per-league CharField affiliations rather than being split across apps.

### Who writes them?

**Existing BotProfile personas.** No new "journalist" archetype needed.

- **Game recaps**: Written by a team-affiliated bot (homer perspective is more entertaining). Selected via `nba_team_abbr` / `nfl_team_abbr` / `epl_team_tla` matching, same as post-match comment selection.
- **Weekly roundups**: Written by a bot with no team affiliation (neutral analyst voice). Any active bot without a team affiliation works, or we can designate one via a new `is_analyst` flag if needed.
- **Betting trend pieces**: Same neutral analyst bot.
- **Cross-league takes**: Same neutral analyst bot (already has multi-league activation flags).

The persona_prompt drives the voice. The article generation service injects game/betting context the same way `comment_service.py` does — personality in the system prompt, data in the user prompt.

### How are they surfaced?

- **Hub homepage**: "Latest News" section below the fold — 3-4 most recent published articles.
- **League dashboard**: League-filtered articles sidebar or section — 2-3 most recent for that league.
- **Dedicated `/news/` route** (hub-level): Full article feed, filterable by league. Paginated.
- **Individual article pages**: `/news/<id_hash>/` with full article body, author bot profile card, link back to game.

### Can users interact?

**Read-only at launch.** No comments on articles. This keeps scope tight and avoids building a second comment system. Can revisit after launch — adding a Comment FK to NewsArticle would be straightforward.

### Generation triggers

| Article Type | Trigger | Timing |
|---|---|---|
| Game Recap | Celery task on game completion | Same hook as `generate_postmatch_comments` — chain or dispatch alongside |
| Weekly Roundup | Celery beat schedule | Monday 10am ET (after full weekend slate) |
| Betting Trend | Celery beat schedule | Wednesday 10am ET (mid-week) |
| Cross-League | Celery beat schedule | Friday 10am ET (weekend preview angle) |

### Cost control

Not a real concern. At Sonnet pricing (~$3/M input, $15/M output):
- ~41 game recaps/week × ~1K output tokens = ~$0.62/week
- 3 roundups + 1 trend + 1 cross-league = ~$0.25/week
- **Total: under $1/week** across all three leagues

Articles use ~2-3x the tokens of a bot comment (800 vs 150 max_tokens), but volume is comparable.

### Quality control

**Auto-publish game recaps** — they're heavily constrained by game data and follow a predictable structure. The post-hoc filter from comment_service (length, profanity) applies here too, just with adjusted thresholds.

**Admin review for trend/roundup/cross-league pieces** — these are more open-ended and higher-stakes (they represent editorial voice, not game reaction). Start as drafts, publish via admin. Graduate to auto-publish once quality is consistent.

---

## Data Model

```python
# news/models.py

class NewsArticle(BaseModel):
    """Auto-generated news article written by a bot personality."""

    class ArticleType(models.TextChoices):
        RECAP = "recap", "Game Recap"
        ROUNDUP = "roundup", "Weekly Roundup"
        TREND = "trend", "Betting Trend"
        CROSS_LEAGUE = "cross_league", "Cross-League"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    # Scope
    league = models.CharField(
        max_length=3, blank=True, db_index=True,
        help_text='"epl", "nba", "nfl", or blank for cross-league',
    )

    # Author — the bot's User account (same pattern as BotComment.user)
    author = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="articles",
    )

    # Content
    article_type = models.CharField(max_length=20, choices=ArticleType.choices)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    body = models.TextField()
    hero_emoji = models.CharField(
        max_length=10, blank=True,
        help_text="Emoji for article card display",
    )

    # Game reference (recaps only) — denormalized to avoid cross-app FKs
    game_id_hash = models.CharField(max_length=12, blank=True, db_index=True)
    game_url = models.CharField(max_length=200, blank=True)
    game_summary = models.CharField(
        max_length=200, blank=True,
        help_text='e.g. "Lakers 112 - Celtics 108"',
    )

    # Publishing
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)

    # Generation metadata (same pattern as BotComment.prompt_used / raw_response)
    prompt_used = models.TextField(blank=True)
    raw_response = models.TextField(blank=True)

    class Meta:
        app_label = "news"
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["league", "status", "-published_at"]),
            models.Index(fields=["article_type", "status"]),
        ]
        constraints = [
            # One recap per game per league (prevent duplicate generation)
            models.UniqueConstraint(
                fields=["league", "game_id_hash"],
                condition=models.Q(article_type="recap", game_id_hash__gt=""),
                name="unique_recap_per_game",
            ),
        ]

    def __str__(self):
        return self.title

    def publish(self):
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at"])
```

### Why denormalized game reference?

The article is a standalone piece of content *generated from* game data at a point in time. It doesn't need a live FK:
- **At generation time**: the service has the full Game object and extracts what it needs into the prompt. It stores `game_id_hash`, `game_url`, and `game_summary` for display.
- **At display time**: the article card shows the game summary text and links to `game_url`. No JOIN needed.
- **For dedup**: the UniqueConstraint on `(league, game_id_hash)` where `article_type=recap` prevents duplicate recaps.

This avoids GenericForeignKey complexity and cross-app FK headaches while preserving everything we need.

---

## Article Generation Service

Follows the same pattern as `comment_service.py` but produces longer-form content.

```python
# news/article_service.py

def generate_game_recap(game, league: str, bot_user) -> NewsArticle | None:
    """
    Generate a game recap article for a completed game.

    Args:
        game: EPL Match, NBA Game, or NFL Game instance
        league: "epl", "nba", or "nfl"
        bot_user: User instance (is_bot=True) who authors the article
    """

    # 1. Build system prompt (bot personality)
    bot_profile = BotProfile.objects.get(user=bot_user)
    system_prompt = bot_profile.persona_prompt

    # 2. Build user prompt (game data + notes + betting context)
    user_prompt = _build_recap_prompt(game, league)

    # 3. Call Claude API
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        temperature=0.9,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # 4. Parse response (structured output: title + body)
    title, body = _parse_article_response(response)

    # 5. Create article
    article = NewsArticle.objects.create(
        league=league,
        author=bot_user,
        article_type=NewsArticle.ArticleType.RECAP,
        title=title,
        body=body,
        game_id_hash=game.id_hash,
        game_url=_get_game_url(game, league),
        game_summary=_format_game_summary(game),
        status=NewsArticle.Status.PUBLISHED,  # auto-publish recaps
        published_at=timezone.now(),
        prompt_used=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
        raw_response=response.content[0].text,
    )
    return article
```

### Prompt structure for recaps

The user prompt follows the same layered approach as `_build_user_prompt()` in comment services:

```
You are writing a game recap article for a sports betting platform.

**Game**: {away_team} {away_score} @ {home_team} {home_score} (FINAL)
**Date**: {game_date}
**Venue**: {venue}

**Box score / key stats**: (league-specific — quarter scores for NFL, etc.)

**Betting line**: {spread} | O/U {total} | ML {moneyline}
**Result vs spread**: {team} covered by {margin}
**Over/under result**: {over_or_under} by {margin}

**Game notes (from a real viewer)**:
{game_notes.body}

**Betting activity**:
- {bet_count} bets placed on this game
- Most popular selection: {most_popular}
- Notable outcomes: {any big wins or bad beats}

Write a 3-5 paragraph game recap article. Include:
1. A punchy, opinionated headline (on its own line, prefixed with TITLE:)
2. A one-sentence subtitle (on its own line, prefixed with SUBTITLE:)
3. The article body

Write in your voice — opinionated, entertaining, with betting angles woven in naturally.
Focus on what actually happened in the game, informed by the game notes.
Reference the spread/total result where relevant.
Keep it under 500 words.
```

### Prompt structure for roundups

```
You are writing a weekly roundup for {league_name} on a sports betting platform.

**Week of {start_date} - {end_date}**

**Results this week**:
{for each game: away_team score @ home_team score — spread result, o/u result}

**Standings movement**:
{notable risers/fallers in standings}

**Betting trends this week**:
- Teams covering: {teams that covered spread}
- Teams not covering: {teams that failed to cover}
- Over/under trend: {X of Y games went over}
- Biggest upset: {game with largest spread miss}

**Top bettors this week**:
{leaderboard movement, notable streaks}

Write a weekly roundup article (4-6 paragraphs). Include:
1. TITLE: line
2. SUBTITLE: line
3. Article body

Cover the biggest storylines, betting trends, and what to watch next week.
Opinionated and entertaining. Under 600 words.
```

---

## App Structure

```
news/
    __init__.py
    apps.py                  # NewsConfig, app_label = "news"
    models.py                # NewsArticle
    admin.py                 # NewsArticleAdmin
    views.py                 # ArticleListView, ArticleDetailView
    urls.py                  # /news/, /news/<id_hash>/
    article_service.py       # generate_game_recap(), generate_weekly_roundup(), etc.
    tasks.py                 # Celery tasks for generation
    context_processors.py    # latest_articles for hub/league templates
    templates/
        news/
            article_list.html
            article_detail.html
            partials/
                article_card.html        # reusable card for feeds
                article_feed.html        # list of cards (HTMX target)
```

### URL routes

```python
# news/urls.py
app_name = "news"

urlpatterns = [
    path("", ArticleListView.as_view(), name="article_list"),
    path("<str:id_hash>/", ArticleDetailView.as_view(), name="article_detail"),
]

# config/urls.py — add:
path("news/", include("news.urls")),
```

### Views

```python
class ArticleListView(ListView):
    model = NewsArticle
    template_name = "news/article_list.html"
    context_object_name = "articles"
    paginate_by = 12

    def get_queryset(self):
        qs = NewsArticle.objects.filter(
            status=NewsArticle.Status.PUBLISHED,
        ).select_related("author__botprofile")
        league = self.request.GET.get("league")
        if league in ("epl", "nba", "nfl"):
            qs = qs.filter(league=league)
        return qs


class ArticleDetailView(DetailView):
    model = NewsArticle
    template_name = "news/article_detail.html"
    context_object_name = "article"
    slug_field = "id_hash"
    slug_url_kwarg = "id_hash"

    def get_queryset(self):
        # Published articles, or drafts for superusers (preview)
        qs = NewsArticle.objects.select_related("author__botprofile")
        if not self.request.user.is_superuser:
            qs = qs.filter(status=NewsArticle.Status.PUBLISHED)
        return qs
```

### Context processor

```python
# news/context_processors.py

def latest_articles(request):
    """Inject latest articles for hub homepage and league dashboards."""
    league = getattr(request, "league", None)
    qs = NewsArticle.objects.filter(
        status=NewsArticle.Status.PUBLISHED,
    ).select_related("author__botprofile")[:4]
    if league:
        qs = qs.filter(league=league)
    return {"latest_articles": qs}
```

---

## Celery Tasks

```python
# news/tasks.py

@shared_task(queue="news")
def generate_game_recap_task(game_id_hash: str, league: str):
    """Generate a recap article for a completed game."""
    game = _get_game(game_id_hash, league)
    bot_user = _select_recap_bot(game, league)  # team-affiliated bot
    generate_game_recap(game, league, bot_user)


@shared_task(queue="news")
def generate_weekly_roundup_task(league: str):
    """Generate a weekly roundup for a league."""
    bot_user = _select_analyst_bot(league)
    generate_weekly_roundup(league, bot_user)


@shared_task(queue="news")
def generate_betting_trend_task(league: str):
    """Generate a mid-week betting trend piece."""
    bot_user = _select_analyst_bot(league)
    generate_betting_trend(league, bot_user)


@shared_task(queue="news")
def generate_cross_league_task():
    """Generate a cross-league weekend preview."""
    bot_user = _select_analyst_bot(league=None)
    generate_cross_league_article(bot_user)
```

### Celery beat schedule

```python
# config/celery.py — add to beat_schedule:

"news-weekly-roundup-epl": {
    "task": "news.tasks.generate_weekly_roundup_task",
    "schedule": crontab(hour=10, minute=0, day_of_week=1),  # Monday 10am
    "args": ("epl",),
},
"news-weekly-roundup-nba": {
    "task": "news.tasks.generate_weekly_roundup_task",
    "schedule": crontab(hour=10, minute=0, day_of_week=1),
    "args": ("nba",),
},
"news-weekly-roundup-nfl": {
    "task": "news.tasks.generate_weekly_roundup_task",
    "schedule": crontab(hour=10, minute=0, day_of_week=1),
    "args": ("nfl",),
},
"news-betting-trend-epl": {
    "task": "news.tasks.generate_betting_trend_task",
    "schedule": crontab(hour=10, minute=0, day_of_week=3),  # Wednesday 10am
    "args": ("epl",),
},
"news-betting-trend-nba": {
    "task": "news.tasks.generate_betting_trend_task",
    "schedule": crontab(hour=10, minute=0, day_of_week=3),
    "args": ("nba",),
},
"news-betting-trend-nfl": {
    "task": "news.tasks.generate_betting_trend_task",
    "schedule": crontab(hour=10, minute=0, day_of_week=3),
    "args": ("nfl",),
},
"news-cross-league": {
    "task": "news.tasks.generate_cross_league_task",
    "schedule": crontab(hour=10, minute=0, day_of_week=5),  # Friday 10am
    "args": (),
},
```

### Hooking into game completion

Game recaps dispatch from the same place post-match comments do. In each league's `tasks.py`, after `generate_postmatch_comments` dispatches:

```python
# In nba/bots/tasks.py generate_postmatch_comments(), after bot comment dispatch:
from news.tasks import generate_game_recap_task
generate_game_recap_task.apply_async(
    args=(game.id_hash, "nba"),
    countdown=random.randint(300, 900),  # 5-15 min after game ends
)
```

Same pattern for EPL and NFL. The delay gives post-match comments time to land first, so the recap feels like a follow-up, not a race.

---

## Admin

```python
# news/admin.py

@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "league", "article_type", "status", "author", "published_at"]
    list_filter = ["league", "article_type", "status"]
    search_fields = ["title", "body"]
    readonly_fields = ["id_hash", "prompt_used", "raw_response", "created_at", "updated_at"]
    raw_id_fields = ["author"]
    actions = ["publish_articles", "archive_articles"]

    def publish_articles(self, request, queryset):
        queryset.filter(status=NewsArticle.Status.DRAFT).update(
            status=NewsArticle.Status.PUBLISHED,
            published_at=timezone.now(),
        )
    publish_articles.short_description = "Publish selected articles"

    def archive_articles(self, request, queryset):
        queryset.update(status=NewsArticle.Status.ARCHIVED)
    archive_articles.short_description = "Archive selected articles"
```

---

## Template Design

### Article card (reusable)

Used on hub homepage, league dashboards, and news feed. Shows:
- Hero emoji + title
- Subtitle (if present)
- Author bot avatar + name
- League badge
- Published time (timesince)
- Game summary (for recaps)

Dark theme, consistent with existing card patterns (featured parlays, bet cards).

### Article detail page

Full article with:
- Title + subtitle
- Author profile card (avatar, name, tagline — links to bot profile)
- Published date
- Game summary with link to game detail page (for recaps)
- Article body (rendered as paragraphs)
- "More from {league}" sidebar with related articles

### Article list page

Grid of article cards. League filter tabs (All / EPL / NBA / NFL). Paginated. HTMX-powered filtering (swap article grid on tab click).

---

## Implementation Sequence

### Phase 1: Foundation
- [ ] Create `news/` app (models, apps, admin)
- [ ] Add to `INSTALLED_APPS`, `makemigrations`, `migrate`
- [ ] Add `path("news/", include("news.urls"))` to `config/urls.py`
- [ ] Basic views (list + detail) with templates
- [ ] Context processor for latest articles
- [ ] Add news section to hub homepage template
- [ ] Add news section to league dashboard templates

### Phase 2: Game Recaps
- [ ] `article_service.py` — `generate_game_recap()` with prompt building
- [ ] League-specific data extractors (`_build_recap_prompt` per league)
- [ ] Response parser (`_parse_article_response`)
- [ ] Post-hoc filter (adapted from comment filter — longer thresholds)
- [ ] Celery task `generate_game_recap_task`
- [ ] Hook into post-match comment dispatch in each league's `tasks.py`
- [ ] Tests: model, service, task, views

### Phase 3: Weekly Roundups
- [ ] `generate_weekly_roundup()` in article_service
- [ ] Aggregate queries: week's results, standings changes, spread/o-u trends
- [ ] Celery beat schedule (Monday 10am)
- [ ] Tests

### Phase 4: Betting Trends
- [ ] `generate_betting_trend()` in article_service
- [ ] Aggregate betting queries: cover rates, popular selections, leaderboard movement
- [ ] Celery beat schedule (Wednesday 10am)
- [ ] Tests

### Phase 5: Cross-League Takes
- [ ] `generate_cross_league_article()` in article_service
- [ ] Cross-league data aggregation (all three leagues' weekly results + trends)
- [ ] Celery beat schedule (Friday 10am)
- [ ] Tests

## Not In Scope (Yet)

- User comments on articles
- User-submitted articles or tips
- External news API ingestion
- Real-time news (push notifications, breaking news)
- SEO optimization / public-facing articles (everything is behind auth for now)
- Article images or media (text-only for now)
