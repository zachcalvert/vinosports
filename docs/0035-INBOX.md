# 0035: Inbox — User Notifications

**Date:** 2026-04-01

## Overview

Add an inbox feature to vinosports: a persistent notification system that alerts users when someone replies to their comments. Notifications surface as an unread badge count on a mail icon in the global navbar and are browsable from a dedicated inbox page in the hub. Each notification includes match/game context and a link to the discussion. Unread notifications auto-dismiss after 48 hours.

## Motivation

Vinosports has real-time toasts (activity feed, badge unlocks, reward distributions) but no persistent notification system. If a user isn't online when someone replies to their comment, they never find out. This kills conversation threads — there's no reason to check back. An inbox gives users a reason to return, creates a feedback loop for discussions, and is a prerequisite for deeper comment threading (see 0036-COMMENT_ARCHITECTURE).

Currently:
- **Toast notifications** are ephemeral — visible for 5-6 seconds, then gone forever.
- **No notification model** exists. The system uses `ActivityEvent` for the public feed and `RewardDistribution.seen` for reward toasts, but there's no general-purpose notification store.
- **No inbox UI** — no mail icon, no notification badge, no dedicated page.
- **WebSocket infrastructure exists** — per-user `NotificationsConsumer` groups (`user_notifications_{pk}`) are already wired up in all three leagues. The channel layer (Redis) is ready.

## Plan

### Phase 1: Notification Model

#### 1.1 Create Model in Core

Add a `Notification` model to the `vinosports.activity` core package. This belongs in core (not a league app) because notifications are cross-league — a user has one inbox regardless of which league the reply came from.

```python
# packages/vinosports-core/src/vinosports/activity/models.py

class Notification(BaseModel):
    """Persistent user notification."""

    class Category(models.TextChoices):
        REPLY = "REPLY", "Reply"
        # Future: MENTION, BET_SETTLEMENT, BADGE, CHALLENGE, etc.

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True, default="")
    url = models.CharField(max_length=300, blank=True, default="")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        help_text="Unread notifications auto-dismiss after this time."
    )

    # Source tracking — which comment triggered this notification
    # Generic enough to support future notification types
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_sent",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.category} → {self.recipient} ({self.id_hash})"
```

Key decisions:
- **`expires_at`** instead of a fixed TTL — set at creation time (`now + 48h`), queryable for cleanup.
- **`actor`** FK — the user who triggered the notification (the replier). Allows rendering "Alice replied to your comment" without parsing the title.
- **`url`** — deep link to the match/game discussion page, including an anchor to the specific comment if possible.
- **`title`** — contains the abbreviated match context (e.g., "EPL — Arsenal vs Chelsea — Mar 29"). Pre-computed at creation time so the inbox can render without joining to match/game tables.
- **`body`** — truncated text of the reply (first ~200 chars). Gives the user enough context to decide whether to click through.

#### 1.2 Migration

```bash
make shell
python manage.py makemigrations activity
python manage.py migrate
```

Since `activity` is a core app with label `activity`, this creates a single migration in `packages/vinosports-core/src/vinosports/activity/migrations/`.

### Phase 2: Notification Creation

#### 2.1 Helper Function

Create a utility to generate reply notifications:

```python
# packages/vinosports-core/src/vinosports/activity/notifications.py

from datetime import timedelta
from django.utils import timezone
from vinosports.activity.models import Notification


NOTIFICATION_TTL = timedelta(hours=48)


def notify_comment_reply(*, parent_comment, reply_comment, match_or_game, league):
    """
    Create a notification for the parent comment's author.

    Args:
        parent_comment: The comment being replied to.
        reply_comment: The new reply.
        match_or_game: The Match or Game instance (for context).
        league: League string ("epl", "nba", "nfl").
    """
    recipient = parent_comment.user
    actor = reply_comment.user

    # Don't notify yourself
    if recipient == actor:
        return None

    # Don't notify bots
    if recipient.is_bot:
        return None

    # Build abbreviated match context
    subject = _build_match_subject(match_or_game, league)

    # Build URL
    url = match_or_game.get_absolute_url()

    # Truncate reply body
    body = reply_comment.body[:200]
    if len(reply_comment.body) > 200:
        body += "..."

    actor_name = actor.display_name or "Someone"
    title = f"{actor_name} replied to your comment — {subject}"

    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        category=Notification.Category.REPLY,
        title=title,
        body=body,
        url=url,
        expires_at=timezone.now() + NOTIFICATION_TTL,
    )


def _build_match_subject(match_or_game, league):
    """
    Build an abbreviated match/game string.
    Format: LEAGUE — Home vs Away — Mon DD

    Examples:
        EPL — Arsenal vs Chelsea — Mar 29
        NBA — LAL vs BOS — Apr 1
        NFL — KC vs BUF — Jan 12
    """
    league_upper = league.upper()
    date_str = match_or_game.start_time.strftime("%b %-d")

    if league == "epl":
        home = match_or_game.home_team.tla  # 3-letter abbreviation
        away = match_or_game.away_team.tla
    else:
        # NBA and NFL use abbreviations
        home = match_or_game.home_team.abbreviation
        away = match_or_game.away_team.abbreviation

    return f"{league_upper} — {home} vs {away} — {date_str}"
```

#### 2.2 Wire Into Comment Reply Views

In each league's `CreateReplyView`, after successfully creating the reply:

```python
# epl/discussions/views.py — CreateReplyView.post()
from vinosports.activity.notifications import notify_comment_reply

# After creating the reply comment:
notification = notify_comment_reply(
    parent_comment=parent,
    reply_comment=reply,
    match_or_game=parent.match,
    league="epl",
)

# Push real-time update via WebSocket (if recipient is online)
if notification:
    _push_notification_ws(notification)
```

Same pattern for NBA (`parent.game`, `league="nba"`) and NFL (`parent.game`, `league="nfl"`).

#### 2.3 Real-Time WebSocket Push

When a notification is created, push it to the recipient's WebSocket group so the navbar badge updates live:

```python
# packages/vinosports-core/src/vinosports/activity/notifications.py

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def _push_notification_ws(notification):
    """Push notification event to recipient's WebSocket group."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_notifications_{notification.recipient.pk}",
        {
            "type": "inbox_notification",
            "count": _unread_count(notification.recipient),
        },
    )


def _unread_count(user):
    """Return current unread notification count."""
    return Notification.objects.filter(
        recipient=user,
        is_read=False,
        expires_at__gt=timezone.now(),
    ).count()
```

The existing `NotificationsConsumer` in each league needs a new handler for this event type:

```python
# Add to NBA/NFL NotificationsConsumer and EPL NotificationConsumer:

def inbox_notification(self, event):
    """Update the unread badge count in the navbar."""
    self.send(text_data=json.dumps({
        "type": "inbox_update",
        "unread_count": event["count"],
    }))
```

### Phase 3: Navbar Badge

#### 3.1 Add Mail Icon to Global Navbar

Insert a mail icon with unread badge between the league switcher and the user menu button in the navbar's right side:

```html
{# In global_navbar.html — inside the authenticated user block, before the user dropdown #}

{% if user.is_authenticated %}
{# Inbox icon with badge #}
<a href="{% url 'hub:inbox' %}"
   class="global-nav-inbox"
   id="inbox-icon"
   aria-label="Inbox{% if unread_notification_count %} ({{ unread_notification_count }} unread){% endif %}">
    <i class="ph-duotone ph-envelope-simple text-xl"></i>
    {% if unread_notification_count %}
    <span class="inbox-badge" id="inbox-badge">{{ unread_notification_count }}</span>
    {% else %}
    <span class="inbox-badge hidden" id="inbox-badge"></span>
    {% endif %}
</a>
{% endif %}
```

#### 3.2 Navbar CSS

```css
/* Add to global_navbar.html <style> block */

.global-nav-inbox {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.375rem;
    border-radius: 0.375rem;
    color: #485f84;
    text-decoration: none;
    transition: color 0.15s, background-color 0.15s;
}
.global-nav-inbox:hover {
    color: #b3262f;
    background-color: rgba(179, 38, 47, 0.06);
}

.inbox-badge {
    position: absolute;
    top: 0;
    right: -0.125rem;
    min-width: 1rem;
    height: 1rem;
    padding: 0 0.25rem;
    border-radius: 9999px;
    background-color: #b3262f;
    color: #ffffff;
    font-size: 0.625rem;
    font-weight: 700;
    line-height: 1rem;
    text-align: center;
    pointer-events: none;
}
.inbox-badge.hidden {
    display: none;
}

/* On mobile, keep the icon but shrink padding */
@media (max-width: 639px) {
    .global-nav-inbox { padding: 0.25rem; }
    .global-nav-inbox i { font-size: 1.125rem; }
}
```

#### 3.3 Context Processor for Unread Count

Add a context processor to inject `unread_notification_count` into every template:

```python
# packages/vinosports-core/src/vinosports/activity/context_processors.py

from django.utils import timezone
from vinosports.activity.models import Notification


def unread_notification_count(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}

    count = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
        expires_at__gt=timezone.now(),
    ).count()

    return {"unread_notification_count": count}
```

Register in `config/settings.py` `TEMPLATES[0]["OPTIONS"]["context_processors"]`.

**Performance note:** This query runs on every page load for authenticated users. The index on `(recipient, is_read, created_at)` makes it a fast index-only scan. If it becomes a concern later, cache in Redis with a short TTL (30s) and invalidate on notification create/read.

#### 3.4 Client-Side Badge Update

Add JavaScript to the base templates (or a shared include) that listens for WebSocket `inbox_update` events and updates the badge without a page reload:

```javascript
// Listen for inbox_update events from the notifications WebSocket
document.addEventListener("DOMContentLoaded", function() {
    // The reward-notifications div already has a ws-connect.
    // We need to handle inbox_update messages from that same connection.
    var badge = document.getElementById("inbox-badge");
    if (!badge) return;

    // HTMX WS extension dispatches htmx:wsAfterMessage for each message
    document.body.addEventListener("htmx:wsAfterMessage", function(e) {
        try {
            var data = JSON.parse(e.detail.message);
            if (data.type === "inbox_update") {
                var count = data.unread_count;
                if (count > 0) {
                    badge.textContent = count > 99 ? "99+" : count;
                    badge.classList.remove("hidden");
                } else {
                    badge.classList.add("hidden");
                }
                // Update aria-label
                var icon = document.getElementById("inbox-icon");
                if (icon) {
                    icon.setAttribute("aria-label",
                        count > 0 ? "Inbox (" + count + " unread)" : "Inbox");
                }
            }
        } catch (err) {
            // Not JSON or not our message — ignore
        }
    });
});
```

### Phase 4: Inbox Page

#### 4.1 View

Create an inbox page in the hub — this is a hub-level feature since notifications span all leagues:

```python
# hub/views.py

from vinosports.activity.models import Notification


class InboxView(LoginRequiredMixin, TemplateView):
    """User's notification inbox."""
    template_name = "hub/inbox.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()

        notifications = (
            Notification.objects
            .filter(
                recipient=self.request.user,
                expires_at__gt=now,
            )
            .select_related("actor")
            .order_by("-created_at")[:100]
        )

        context["notifications"] = notifications
        context["unread_count"] = sum(1 for n in notifications if not n.is_read)
        return context
```

#### 4.2 URL

```python
# hub/urls.py
path("inbox/", views.InboxView.as_view(), name="inbox"),
```

#### 4.3 Mark As Read

Two mechanisms:

**a) Mark individual notification as read (on click):**

```python
class MarkNotificationReadView(LoginRequiredMixin, View):
    """Mark a single notification as read and redirect to its URL."""

    def post(self, request, id_hash):
        notification = get_object_or_404(
            Notification,
            id_hash=id_hash,
            recipient=request.user,
        )
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])

        # If HTMX request, return updated row
        if request.headers.get("HX-Request"):
            return render(request, "hub/partials/inbox_notification.html", {
                "notification": notification,
            })

        # Otherwise redirect to the notification's target
        return redirect(notification.url or "hub:inbox")
```

**b) Mark all as read:**

```python
class MarkAllReadView(LoginRequiredMixin, View):
    """Mark all unread notifications as read."""

    def post(self, request):
        Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        if request.headers.get("HX-Request"):
            return HttpResponse(headers={"HX-Refresh": "true"})
        return redirect("hub:inbox")
```

URLs:

```python
path("inbox/read/<str:id_hash>/", views.MarkNotificationReadView.as_view(), name="inbox_mark_read"),
path("inbox/read-all/", views.MarkAllReadView.as_view(), name="inbox_mark_all_read"),
```

#### 4.4 Inbox Template

```html
{# hub/templates/hub/inbox.html #}
{% extends "hub/base.html" %}
{% block title %}Inbox — Vino Sports{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-8">
    {# Header #}
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-xl font-bold text-white">
            Inbox
            {% if unread_count %}
            <span class="text-sm font-normal text-gray-400">({{ unread_count }} unread)</span>
            {% endif %}
        </h1>
        {% if unread_count %}
        <form method="post" action="{% url 'hub:inbox_mark_all_read' %}">
            {% csrf_token %}
            <button type="submit"
                    class="text-sm text-gray-400 hover:text-white transition"
                    hx-post="{% url 'hub:inbox_mark_all_read' %}"
                    hx-swap="none">
                Mark all as read
            </button>
        </form>
        {% endif %}
    </div>

    {# Notification list #}
    <div class="space-y-1">
        {% for notification in notifications %}
            {% include "hub/partials/inbox_notification.html" with notification=notification %}
        {% empty %}
            <div class="text-center py-16">
                <i class="ph-duotone ph-envelope-simple text-4xl text-gray-600 mb-3"></i>
                <p class="text-gray-500">No notifications yet.</p>
                <p class="text-sm text-gray-600 mt-1">You'll be notified when someone replies to your comments.</p>
            </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

#### 4.5 Notification Row Partial

```html
{# hub/templates/hub/partials/inbox_notification.html #}

<div class="flex items-start gap-3 p-3 rounded-lg transition
    {% if not notification.is_read %}bg-gray-800/60 border border-gray-700{% else %}bg-transparent{% endif %}"
    id="notification-{{ notification.id_hash }}">

    {# Actor avatar #}
    <div class="flex-shrink-0 mt-0.5">
        {% if notification.actor and notification.actor.profile_image %}
        <img src="{{ notification.actor.profile_image.url }}" alt=""
             class="w-8 h-8 rounded-full object-cover">
        {% else %}
        <div class="w-8 h-8 rounded-full flex items-center justify-center"
             style="background-color: {{ notification.actor.avatar_bg|default:'#374151' }}">
            <i class="ph-duotone ph-{{ notification.actor.avatar_icon|default:'user-circle' }} text-sm text-white"></i>
        </div>
        {% endif %}
    </div>

    {# Content #}
    <div class="flex-1 min-w-0">
        <a href="{{ notification.url }}"
           class="block group"
           hx-post="{% url 'hub:inbox_mark_read' id_hash=notification.id_hash %}"
           hx-target="#notification-{{ notification.id_hash }}"
           hx-swap="outerHTML">
            <p class="text-sm {% if not notification.is_read %}text-white font-medium{% else %}text-gray-400{% endif %} group-hover:text-blue-400 transition">
                {{ notification.title }}
            </p>
            {% if notification.body %}
            <p class="text-xs text-gray-500 mt-0.5 truncate">{{ notification.body }}</p>
            {% endif %}
        </a>
        <p class="text-xs text-gray-600 mt-1">{{ notification.created_at|timesince }} ago</p>
    </div>

    {# Unread indicator #}
    {% if not notification.is_read %}
    <div class="flex-shrink-0 mt-2">
        <span class="w-2 h-2 rounded-full bg-blue-500 inline-block"></span>
    </div>
    {% endif %}
</div>
```

The link uses a combined pattern: clicking navigates to the match/game (via `href`), and simultaneously fires an HTMX POST to mark the notification as read (swapping the row to remove the unread styling). The HTMX request fires first, then the navigation proceeds via `hx-boost`.

### Phase 5: Auto-Dismiss Expired Notifications

#### 5.1 Celery Task

Add a periodic task to clean up expired unread notifications:

```python
# packages/vinosports-core/src/vinosports/activity/tasks.py

from celery import shared_task
from django.utils import timezone
from vinosports.activity.models import Notification


@shared_task
def dismiss_expired_notifications():
    """
    Delete unread notifications past their expiry.
    Runs every hour via Celery beat.
    """
    expired = Notification.objects.filter(
        is_read=False,
        expires_at__lte=timezone.now(),
    )
    count = expired.count()
    expired.delete()
    return f"Dismissed {count} expired notifications"
```

#### 5.2 Celery Beat Schedule

Add to `config/celery.py`:

```python
app.conf.beat_schedule["dismiss-expired-notifications"] = {
    "task": "vinosports.activity.tasks.dismiss_expired_notifications",
    "schedule": 3600.0,  # Every hour
}
```

#### 5.3 Retention Policy for Read Notifications

Read notifications don't expire via the 48h TTL (that only applies to unread), but they should still be cleaned up eventually. Delete read notifications older than 30 days in the same task:

```python
# Also in dismiss_expired_notifications():
old_read = Notification.objects.filter(
    is_read=True,
    created_at__lte=timezone.now() - timedelta(days=30),
)
old_count = old_read.count()
old_read.delete()
return f"Dismissed {count} expired, {old_count} old read notifications"
```

## Relationship to 0036 (Comment Architecture)

This doc provides the infrastructure that 0036's "Phase 2.3: Notification on Reply" depends on. Specifically:

- **0035 provides:** `Notification` model, `notify_comment_reply()` helper, WebSocket `inbox_notification` event type, navbar badge, inbox page.
- **0036 consumes:** Calls `notify_comment_reply()` from reply views. The "encourage replies" phase in 0036 assumes the inbox exists.

Build order: **0035 first**, then 0036.

## Files Affected

| Area | Files |
|------|-------|
| Core model | `packages/vinosports-core/src/vinosports/activity/models.py` (add Notification) |
| Core migration | `packages/vinosports-core/src/vinosports/activity/migrations/` (new) |
| Notification helpers | `packages/vinosports-core/src/vinosports/activity/notifications.py` (new) |
| Context processor | `packages/vinosports-core/src/vinosports/activity/context_processors.py` (new) |
| Celery task | `packages/vinosports-core/src/vinosports/activity/tasks.py` (new) |
| Celery beat config | `config/celery.py` |
| Settings | `config/settings.py` (add context processor) |
| Global navbar | `packages/vinosports-core/src/vinosports/templates/vinosports/components/global_navbar.html` |
| Hub views | `hub/views.py` (InboxView, MarkNotificationReadView, MarkAllReadView) |
| Hub URLs | `hub/urls.py` |
| Inbox template | `hub/templates/hub/inbox.html` (new) |
| Inbox partial | `hub/templates/hub/partials/inbox_notification.html` (new) |
| Reply views | `epl/discussions/views.py`, `nba/discussions/views.py`, `nfl/discussions/views.py` (call notify_comment_reply) |
| WS consumers | `nba/activity/consumers.py`, `nfl/activity/consumers.py`, `epl/rewards/consumers.py` (add inbox_notification handler) |
| Base templates | All league base templates (JS for badge update via htmx:wsAfterMessage) |

## Testing

- **Model tests:** Notification creation, expiry filtering, `is_read` transitions.
- **Helper tests:** `notify_comment_reply()` — creates notification with correct title/body/url, skips self-replies, skips bot recipients.
- **View tests:** InboxView lists only recipient's non-expired notifications. MarkNotificationReadView sets `is_read=True`. MarkAllReadView bulk-updates.
- **Context processor tests:** Returns correct unread count, returns 0 for anonymous users.
- **Celery task tests:** `dismiss_expired_notifications` deletes expired unread and old read notifications.
- **WebSocket tests:** `inbox_notification` event delivers correct unread count to recipient's consumer.
- **Integration tests:** Full flow — create reply → notification created → WebSocket push → badge updates → click marks read.

## Rollout Order

1. **Phase 1** — Notification model + migration. Foundation for everything else.
2. **Phase 3** — Navbar badge + context processor. Visible immediately even with no notifications yet.
3. **Phase 4** — Inbox page. Users can now browse notifications.
4. **Phase 2** — Wire notification creation into reply views + WebSocket push. This is when notifications start flowing.
5. **Phase 5** — Celery task for expiry cleanup. Can be added any time after Phase 1.
