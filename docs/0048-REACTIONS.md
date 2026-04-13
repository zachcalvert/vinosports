# 0048 — Reactions

Status: **Implemented**

## Overview

Emoji reactions on comments and news articles. Users can react once per item. Bots are dispatched to react when new comments and articles are published, mirroring the prop bet bot dispatch pattern.

## Scope

### Reaction Types (initial)

| Key | Emoji | Meaning |
|-----|-------|---------|
| `thumbs_up` | 👍 | Agree / like |
| `thumbs_down` | 👎 | Disagree / dislike |
| `party_cup` | 🥤 | Cheers / party |

Stored as a `CharField` with choices — easy to extend later without a migration (just add a choice).

### Rules

- A user may have **at most one reaction** per target (comment or article)
- Selecting a different emoji replaces the existing reaction (swap, not stack)
- Selecting the same emoji removes the reaction (toggle off)
- Bots react to comments and articles shortly after publication

## Data Model

### Option A: Single abstract model, two concrete models (recommended)

```python
# packages/vinosports-core/src/vinosports/reactions/models.py

class ReactionType(models.TextChoices):
    THUMBS_UP = "thumbs_up", "👍"
    THUMBS_DOWN = "thumbs_down", "👎"
    PARTY_CUP = "party_cup", "🥤"


class AbstractReaction(BaseModel):
    """Base reaction — concrete subclasses add the target FK."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="%(app_label)s_%(class)s_reactions")
    reaction_type = models.CharField(max_length=20, choices=ReactionType.choices)

    class Meta:
        abstract = True
```

Two concrete models in the same core `reactions` app:

```python
class CommentReaction(AbstractReaction):
    """Reaction on a comment. Uses GenericForeignKey to support all league Comment models."""
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    comment = GenericForeignKey("content_type", "object_id")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content_type", "object_id"],
                name="unique_comment_reaction",
            ),
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]


class ArticleReaction(AbstractReaction):
    """Reaction on a NewsArticle."""
    article = models.ForeignKey("news.NewsArticle", on_delete=models.CASCADE,
                                related_name="reactions")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "article"],
                name="unique_article_reaction",
            ),
        ]
```

**Why GenericForeignKey for comments?** Comments are concrete per league (`epl_discussions.Comment`, `nba_discussions.Comment`, etc.) — there's no single FK target. A GenericFK lets one table cover all leagues. Articles are a single model, so a direct FK is simpler.

**Why not per-league reaction models?** Reactions have no league-specific fields. Unlike comments (which have a match/game FK), reactions only point at the thing being reacted to. One table per target type keeps it simple.

### Option B: Per-league concrete models (same pattern as comments)

Create `AbstractReaction` in core, then `epl/reactions/models.py` with `CommentReaction(AbstractReaction)` pointing at `epl_discussions.Comment`, etc. Skip GenericFK.

**Pro:** No contenttypes overhead, simpler queries.
**Con:** 5 new apps (one per league) for a model with no league-specific fields. More migrations, more admin registrations, more boilerplate.

### Recommendation

**Option A.** Reactions are uniform across leagues — they don't carry league-specific data. The GenericFK cost is low (one extra join) and pays for itself in reduced boilerplate. If performance becomes an issue, we can denormalize counts onto the comment model later.

## API / Views

### Endpoints

All reactions go through a single core reactions app. League routing is not needed.

```
POST   /reactions/comment/<content_type_id>/<object_id>/<reaction_type>/   → toggle reaction
POST   /reactions/article/<article_id_hash>/<reaction_type>/               → toggle reaction
```

Toggle semantics: if the user already reacted with the same emoji, remove it. If the user reacted with a different emoji, swap to the new one. If no reaction exists, create it. Returns an HTMX partial with updated counts.

### Response (HTMX partial)

```html
<!-- reactions/partials/reaction_buttons.html -->
<div class="flex items-center gap-2" id="reactions-{target_type}-{target_id}">
  <button hx-post="..." hx-target="#reactions-..." hx-swap="outerHTML"
          class="... {active_class}">
    👍 <span>3</span>
  </button>
  <button ...>👎 <span>1</span></button>
  <button ...>🥤 <span>7</span></button>
</div>
```

- Active state: highlight border/background when the current user has reacted
- Anonymous users: show counts but no buttons (or buttons that redirect to login)

### Query Efficiency

Aggregate counts in a single query per target:

```python
from django.db.models import Count, Q

def get_reaction_summary(content_type_id, object_id, user=None):
    qs = CommentReaction.objects.filter(
        content_type_id=content_type_id, object_id=object_id
    )
    counts = qs.values("reaction_type").annotate(count=Count("id"))
    user_reactions = set()
    if user and user.is_authenticated:
        user_reactions = set(qs.filter(user=user).values_list("reaction_type", flat=True))
    return counts, user_reactions
```

For comment lists (N comments), use a prefetch or bulk query to avoid N+1:

```python
# Bulk fetch all reactions for a list of comments
CommentReaction.objects.filter(
    content_type=comment_ct,
    object_id__in=comment_ids,
).values("object_id", "reaction_type").annotate(count=Count("id"))
```

## UI Integration

### Comments

Add reaction buttons below each comment, next to the existing "Reply" action:

```
┌──────────────────────────────────────────┐
│ @username · 5m ago                       │
│ Great match, didn't see that coming!     │
│                                          │
│ 👍 3   👎 1   🥤 7          Reply        │
└──────────────────────────────────────────┘
```

- Buttons are inline, compact, using the existing Tailwind utility classes
- Active reactions get a subtle highlight (e.g. `bg-blue-500/10 border-blue-500/30`)
- HTMX swaps just the reaction button group on toggle

### News Articles

Add reaction buttons at the bottom of the article detail page, below the article body.

### Template Include

A single reusable partial that takes `target_type`, `target_id`, `counts`, and `user_reactions`:

```django
{% include "reactions/partials/reaction_buttons.html" with target_type="comment" target_id=comment.pk counts=comment.reaction_counts user_reactions=user_reaction_set %}
```

This partial is included from each league's `comment_single.html` and from the news article detail template.

## Bot Reactions

### Dispatch Pattern

Follow the same pattern as `place_bot_prop_bets`:

```python
@shared_task(name="vinosports.bots.tasks.dispatch_bot_reactions")
def dispatch_bot_reactions(target_type, target_id):
    """Dispatch 2-6 bots to react to a comment or article."""
    # Pick 2-6 random active bots (exclude the author)
    # For each bot, dispatch react_as_bot.apply_async() with staggered delays (10-60s)
```

```python
@shared_task(name="vinosports.bots.tasks.react_as_bot")
def react_as_bot(bot_user_id, target_type, target_id):
    """Single bot reacts to a target."""
    # Pick a reaction type (weighted random, personality-influenced)
    # Create the reaction (skip if already exists)
```

### Trigger Points

1. **Comment created** — after a human user posts a comment, dispatch bot reactions
2. **News article published** — after `article.publish()` is called, dispatch bot reactions
3. **Bot comment posted** — optionally, other bots can react to bot comments too (adds liveliness)

### Reaction Selection

Bots pick reactions based on lightweight personality heuristics (no LLM call needed):

- **Strategy-based weighting:** `CHAOS_AGENT` leans toward 🥤, `FRONTRUNNER` leans toward 👍 on favorites
- **Simple random with bias:** 60% 👍, 20% 🥤, 20% 👎 as a baseline, shifted by personality
- **No LLM call** — reactions are simple enough that random selection with personality bias is sufficient

### Not every bot reacts

- Pick 2-6 bots per target (fewer than the 3-5 for prop bets, since reactions are lighter)
- Stagger delays: 10-60 seconds after publication
- Skip if the bot authored the comment/article being reacted to

## Implementation Plan

### Phase 1: Core Models + Migrations

1. Create `packages/vinosports-core/src/vinosports/reactions/` app
2. Add `AbstractReaction`, `CommentReaction`, `ArticleReaction` models
3. Add `ReactionType` choices
4. Register in `INSTALLED_APPS` (as `reactions`)
5. Generate and run migrations

### Phase 2: Views + URLs

1. Add toggle view (handles both create and delete)
2. Wire up URL patterns in `config/urls.py` under `/reactions/`
3. Create HTMX partial template for reaction buttons
4. Add bulk query helper for comment list prefetching

### Phase 3: UI Integration

1. Add reaction button partial include to each league's `comment_single.html` (EPL, NBA, NFL, WC, UCL)
2. Add reaction buttons to news article detail template
3. Style active/inactive states
4. Handle anonymous users (show counts, hide/disable buttons)

### Phase 4: Bot Reactions

1. Add `dispatch_bot_reactions` and `react_as_bot` Celery tasks
2. Add personality-based reaction weighting logic
3. Wire dispatch into comment creation flow (after human comment is saved)
4. Wire dispatch into article publish flow
5. Optionally dispatch on bot comments for cross-bot reactions

### Phase 5: Polish

1. Add reaction counts to admin list displays
2. Add tests (model constraints, toggle behavior, bot dispatch, bulk queries)
3. Consider WebSocket broadcast for real-time reaction count updates (if discussions already use WS)

## Resolved Questions

1. **Thumbs up/down mutually exclusive?** Yes — one reaction per user per target. Selecting a different emoji swaps; same emoji toggles off.
2. **Denormalize reaction counts?** No. Calculate on the fly — max 50 users, no performance concern.
3. **Show who reacted?** Yes, as a hover tooltip — deferred to Phase 5.
4. **Max bot reactions per day?** No cap needed. Reactions are cheap and don't affect balance.
