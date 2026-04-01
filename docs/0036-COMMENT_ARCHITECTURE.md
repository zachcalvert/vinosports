# 0036: Comment Architecture Investment

**Date:** 2026-04-01

## Overview

Deepen the comment/discussion system across all leagues: support third-level replies (grandchild comments), encourage more engagement through UX improvements, and make bots responsive to human comments in real time.

## Motivation

Comments are the social backbone of vinosports. Right now the system caps reply depth at one level (comment → reply, no reply-to-reply), which flattens conversations and discourages back-and-forth. Bots comment on matches via scheduled triggers but don't reliably respond when a human joins the conversation. The result is a discussion section that feels like a bulletin board instead of a live community.

Goals:
1. **Third-level replies** — Let users reply to replies (grandchild comments), enabling real threaded conversations without going to infinite nesting.
2. **Encourage replies** — UX and notification nudges that make replying feel natural and rewarding.
3. **Bot-replies-to-humans** — When a human comments, relevant bots should reply, making the discussion feel alive even at low user counts.

## Current State

### Models
- `AbstractComment` in `vinosports.discussions.models` has a self-referential `parent` FK enabling one level of threading.
- League models (`epl.discussions.Comment`, `nba.discussions.Comment`, `nfl.discussions.Comment`) add match/game FKs and indexes on `(match/game, created_at)` and `parent`.

### Views
- `CreateReplyView` in each league explicitly rejects replies to replies: `if parent.parent_id is not None: return error`.
- Deleted comments with replies show as `[Comment deleted]` placeholders to preserve thread context.
- EPL has `CommentListView` with pagination (20/page). NBA and NFL do not.

### Bot Comments
- `AbstractBotComment` tracks trigger type (`PRE_MATCH`, `POST_BET`, `POST_MATCH`, `REPLY`), prompt, raw response, and filtered flag.
- Dedup via unique constraint on `(user, match/game, trigger_type)`.
- EPL's `comment_service.py` has full bot reply logic: affinity maps, homer detection, ~30% random gate for human replies, per-match cap of 4 replies.
- NBA has limited bot comment support. NFL has bot models but no comment service.
- `maybe_reply_to_human_comment` task exists in EPL only; called from `CreateCommentView` when the author is not a bot.

### Templates
- Comment templates are recursive: `comment_single.html` includes itself with `is_reply=True` to suppress the reply button on nested comments.
- Reply forms are hidden by default, toggled via inline `onclick`.

## Plan

### Phase 1: Third-Level Replies (Model + View + Template)

#### 1.1 Update AbstractComment (core)

No model change needed — the self-referential `parent` FK already supports arbitrary depth. The one-level constraint is enforced in views and templates, not the schema.

Add a helper method to `AbstractComment`:

```python
@property
def root_comment(self):
    """Walk up to the top-level comment."""
    comment = self
    while comment.parent_id is not None:
        comment = comment.parent
    return comment

@property
def depth(self):
    """Return nesting depth (0 = top-level, 1 = reply, 2 = grandchild)."""
    d = 0
    comment = self
    while comment.parent_id is not None:
        d += 1
        comment = comment.parent
    return d
```

These are used in views to enforce max depth and in templates to control indentation.

#### 1.2 Update Reply Views (all leagues)

Change `CreateReplyView` to allow depth up to 2 (grandchild):

```python
# Before
if parent.parent_id is not None:
    return HttpResponseBadRequest("Cannot reply to a reply.")

# After
if parent.depth >= 2:
    return HttpResponseBadRequest("Maximum reply depth reached.")
```

For grandchild replies, `parent` is set to the reply being responded to (not normalized to root). This preserves the exact reply-to relationship while capping depth at 3 levels total.

#### 1.3 Update Comment Templates (all leagues)

Currently templates use `is_reply` boolean to toggle reply buttons. Replace with depth-aware logic:

```html
{# Indentation scales with depth #}
<div class="{% if depth == 1 %}ml-8 pl-4 border-l{% elif depth == 2 %}ml-16 pl-4 border-l{% endif %}">
    ...
    {# Reply button shown for depth 0 and 1 only #}
    {% if depth < 2 and user.is_authenticated %}
        <button @click="showReply = !showReply">Reply</button>
    {% endif %}

    {# Render children recursively #}
    {% for child in comment.visible_replies %}
        {% include "comment_single.html" with comment=child depth=depth|add:1 %}
    {% endfor %}
</div>
```

#### 1.4 Update Prefetch Strategy

Current views prefetch one level of replies. Extend to two levels:

```python
comments = (
    Comment.objects
    .filter(match=match, parent__isnull=True)
    .select_related("user")
    .prefetch_related(
        Prefetch(
            "replies",
            queryset=Comment.objects.filter(is_deleted=False)
                .select_related("user")
                .prefetch_related(
                    Prefetch(
                        "replies",
                        queryset=Comment.objects.filter(is_deleted=False)
                            .select_related("user"),
                        to_attr="visible_grandchildren",
                    )
                ),
            to_attr="visible_replies",
        )
    )
)
```

This is 3 queries total (top-level + replies + grandchildren), not N+1.

#### 1.5 Update Bot Reply Normalization

Currently bot replies normalize to the top-level comment:
```python
reply_parent = parent_comment.parent or parent_comment
```

Update to preserve the actual reply target (since we now support depth 2):
```python
reply_parent = parent_comment  # reply directly to the comment being responded to
# But cap at depth 2
if parent_comment.depth >= 2:
    reply_parent = parent_comment.parent  # attach to the reply instead
```

### Phase 2: Encourage Replies

#### 2.1 Inline Reply Prompt

When a comment has zero replies, show a subtle CTA below it:

```html
{% if comment.reply_count == 0 and user.is_authenticated %}
<button class="text-xs text-gray-400 hover:text-gray-300 mt-1"
        @click="showReply = !showReply">
    Be the first to reply
</button>
{% endif %}
```

#### 2.2 Reply Count Badge

Show reply count on comments with threads:

```html
{% if comment.reply_count > 0 %}
<span class="text-xs text-gray-400">
    {{ comment.reply_count }} repl{{ comment.reply_count|pluralize:"y,ies" }}
</span>
{% endif %}
```

Annotate `reply_count` in the queryset rather than computing per-template:

```python
from django.db.models import Count

comments = comments.annotate(reply_count=Count("replies", filter=Q(replies__is_deleted=False)))
```

#### 2.3 Notification on Reply (WebSocket)

When someone replies to your comment, send a real-time notification via the existing per-user notification WebSocket group:

```python
# In CreateReplyView, after creating the reply:
if parent.user != request.user:
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_notifications_{parent.user.pk}",
        {
            "type": "notification",
            "category": "reply",
            "message": f"{request.user.display_name} replied to your comment",
            "url": match_or_game_url,
        },
    )
```

This uses the existing `NotificationsConsumer` infrastructure already present in NBA and NFL. EPL's `NotificationConsumer` in `epl/rewards/consumers.py` handles the same message types.

#### 2.4 "Discussion Active" Indicator

On match/game cards, show a flame or chat icon when a match has recent comment activity (last 30 minutes):

```python
# In match list context processor
from django.utils import timezone
active_cutoff = timezone.now() - timedelta(minutes=30)
active_discussions = set(
    Comment.objects.filter(
        match__in=matches,
        created_at__gte=active_cutoff,
        is_deleted=False,
    ).values_list("match_id", flat=True)
)
```

Display on the card:
```html
{% if match.id in active_discussions %}
<span class="text-xs text-amber-400" title="Active discussion">
    <i class="ph ph-chat-circle-dots"></i>
</span>
{% endif %}
```

### Phase 3: Bots Reply to Human Comments

#### 3.1 Extend `maybe_reply_to_human_comment` to NBA and NFL

EPL already has this task. Port it to NBA and NFL:

1. **NBA** (`nba/bots/tasks.py`): Create `maybe_reply_to_human_comment` task mirroring EPL's logic. Wire it into `nba.discussions.views.CreateCommentView` post-save.
2. **NFL** (`nfl/bots/tasks.py`): Same as NBA. Also requires creating a `comment_service.py` in `nfl/bots/` (currently missing).

#### 3.2 Increase Bot Reply Probability

The current ~30% random gate for human replies is too conservative for a platform still growing its user base. Increase to ~70% for now:

```python
# comment_service.py
HUMAN_REPLY_PROBABILITY = 0.7  # was 0.3
```

Make this configurable via `SiteSettings` so it can be tuned without a deploy:

```python
# hub/models.py - SiteSettings
bot_reply_probability = models.FloatField(default=0.7, help_text="Probability a bot replies to a human comment (0.0-1.0)")
```

#### 3.3 Smarter Bot Selection for Replies

Current logic picks from relevant bots randomly. Improve by:

1. **Prefer bots who haven't commented on this match yet** — avoids one bot dominating.
2. **Prefer bots with affinity to the match** — homer bots for their team, strategy-matched bots for the odds profile.
3. **Vary response delay** — currently 30s-5min random. Add a shorter range (10s-60s) for replies to make conversations feel snappier.

```python
def select_reply_bot(match, parent_comment):
    """Pick the best bot to reply to a human comment."""
    eligible = BotProfile.objects.filter(
        active_in_epl=True,  # or active_in_nba / active_in_nfl
        user__is_active=True,
    ).exclude(user=parent_comment.user)

    # Score bots by relevance
    scored = []
    for bot in eligible:
        score = 0
        # Has this bot already commented on this match?
        existing = BotComment.objects.filter(user=bot.user, match=match).count()
        if existing == 0:
            score += 2  # prefer fresh voices
        # Is this bot a homer for a team in this match?
        if is_homer_relevant(bot, match):
            score += 3
        # Strategy relevance
        if is_strategy_relevant(bot, match):
            score += 1
        scored.append((score, random.random(), bot))  # random tiebreak

    scored.sort(reverse=True)
    return scored[0][2] if scored else None
```

#### 3.4 Reply Context in Bot Prompts

When a bot replies to a human comment, the prompt should include:

- The human's comment text
- The human's bet position on the match (if any)
- Recent thread context (up to 3 previous comments in the thread)

This is partially implemented in EPL's `comment_service.py` (includes quoted parent comment). Extend to include thread context:

```python
thread_context = ""
if parent_comment:
    # Walk up the thread to get context
    ancestors = []
    c = parent_comment
    while c and len(ancestors) < 3:
        ancestors.append(c)
        c = c.parent if c.parent_id else None

    for ancestor in reversed(ancestors):
        name = ancestor.user.display_name or "Anonymous"
        thread_context += f"{name}: \"{ancestor.body}\"\n"

    user_prompt += f"\n\nThread context:\n{thread_context}"
    user_prompt += f"\nReply to {parent_comment.user.display_name}'s comment above."
```

## Migration Plan

No database migrations required for Phase 1 (depth support is already in the schema). Phase 3.2 (SiteSettings field) requires a migration.

## Rollout Order

1. **Phase 3.1 + 3.2** — Bot replies to humans in NBA/NFL. Highest impact for engagement with lowest risk.
2. **Phase 2.1 + 2.2** — Reply encouragement UX. Small template changes.
3. **Phase 1** — Third-level replies. View + template + prefetch changes across all leagues.
4. **Phase 2.3** — Reply notifications via WebSocket.
5. **Phase 2.4** — Active discussion indicators.
6. **Phase 3.3 + 3.4** — Smarter bot selection and richer prompts.

## Files Affected

| Area | Files |
|------|-------|
| Core model | `packages/vinosports-core/src/vinosports/discussions/models.py` |
| EPL views | `epl/discussions/views.py` |
| NBA views | `nba/discussions/views.py` |
| NFL views | `nfl/discussions/views.py` |
| EPL templates | `epl/discussions/templates/epl_discussions/partials/comment_single.html` |
| NBA templates | `nba/discussions/templates/nba_discussions/partials/comment.html` |
| NFL templates | `nfl/discussions/templates/nfl_discussions/partials/comment.html` |
| EPL bot service | `epl/bots/comment_service.py` |
| NBA bot tasks | `nba/bots/tasks.py` (new task) |
| NFL bot service | `nfl/bots/comment_service.py` (new file) |
| NFL bot tasks | `nfl/bots/tasks.py` (new task) |
| Hub settings | `hub/models.py` (SiteSettings field) |
| WebSocket notifications | `epl/rewards/consumers.py`, `nba/activity/consumers.py`, `nfl/activity/consumers.py` |
| Context processors | `epl/matches/context_processors.py`, `nba/games/context_processors.py`, `nfl/games/context_processors.py` |

## Testing

- **Unit tests:** Reply depth validation (depth 0, 1, 2 allowed; depth 3 rejected), bot selection scoring, thread context building.
- **Integration tests:** Full comment → bot reply pipeline with `task_always_eager=True`.
- **WebSocket tests:** Reply notification delivery via `WebsocketCommunicator`.
- **Template tests:** Verify indentation classes at each depth level.
