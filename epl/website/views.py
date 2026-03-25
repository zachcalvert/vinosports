from heapq import merge
from operator import attrgetter

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from epl.activity.models import ActivityEvent
from epl.betting.forms import CurrencyForm, DisplayNameForm
from epl.betting.models import BetSlip, Parlay
from epl.discussions.models import Comment
from epl.matches.models import Team
from epl.users.avatars import AVATAR_COLORS, AVATAR_ICONS, get_unlocked_frames
from epl.users.forms import AvatarForm
from epl.website.theme import THEME_SESSION_KEY, get_theme, normalize_theme
from vinosports.betting.leaderboard import (
    get_public_identity,
    get_user_rank,
    mask_email,
)
from vinosports.betting.models import (
    Badge,
    UserBadge,
    UserBalance,
    UserStats,
)

ARCHITECTURE_COMPONENTS = {
    "browser": {
        "label": "Browser",
        "subtitle": "Django Templates + HTMX + WebSocket",
        "description": "Pages are served as full HTML from Django templates. HTMX handles partial page updates, form submissions, and auto-polling — all without a JavaScript framework. The htmx-ext-ws extension connects to Django Channels for live score updates over WebSocket.",
        "tech": ["Django Templates", "HTMX 2.0", "htmx-ext-ws", "Tailwind CSS"],
        "pages": [
            "Dashboard (live scores via WS)",
            "Fixtures (matchday tabs via hx-get)",
            "Odds Board (30s polling)",
            "Match Detail (odds + bet form)",
            "My Bets (bet history)",
        ],
    },
    "django": {
        "label": "Django",
        "subtitle": "Views, Models, ORM, Admin",
        "description": "The core application server. Django handles HTTP routing, renders templates, manages the ORM and migrations, and provides the admin interface. Views serve both full pages and HTMX partials depending on the request.",
        "tech": ["Django 5.x", "Gunicorn", "Django ORM", "Admin Site"],
        "pages": [
            "6 models (Match, Team, Standing, Odds, BetSlip, UserBalance)",
            "Class-based views for all pages",
            "HTMX-aware partial responses",
            "Full admin panel for data inspection",
        ],
    },
    "channels": {
        "label": "Daphne / Channels",
        "subtitle": "ASGI + WebSocket Consumers",
        "description": "Daphne serves as the ASGI server, handling both HTTP and WebSocket connections. Django Channels provides WebSocket consumers that join channel groups per match, broadcasting score updates in real time as HTML partials.",
        "tech": [
            "Daphne (ASGI)",
            "Django Channels",
            "Channel Layers",
            "WebSocket Consumers",
        ],
        "pages": [
            "DashboardConsumer — broadcasts all live match updates",
            "MatchConsumer — per-match score and status updates",
            "Out-of-band (OOB) HTML swaps for live DOM updates",
        ],
    },
    "redis": {
        "label": "Redis",
        "subtitle": "Cache + Broker + Channel Layer",
        "description": "Redis plays three roles in one service: it caches API responses and computed data, acts as the Celery message broker for task queuing, and serves as the Django Channels layer backend for WebSocket pub/sub messaging.",
        "tech": [
            "Redis 7.x",
            "django-redis (cache)",
            "Celery broker",
            "channels-redis",
        ],
        "pages": [
            "Cache: API responses, computed odds",
            "Broker: Celery task queue and results",
            "Channel Layer: WebSocket group messaging",
        ],
    },
    "postgresql": {
        "label": "PostgreSQL",
        "subtitle": "Persistent Data Store",
        "description": "All application data lives in PostgreSQL. The Django ORM handles schema migrations, queries, and transactions. Atomic operations ensure bet placement deducts balances safely.",
        "tech": ["PostgreSQL 16", "Django ORM", "Migrations", "Atomic Transactions"],
        "pages": [
            "Match, Team, Standing — core football data",
            "Odds — bookmaker odds snapshots",
            "BetSlip, UserBalance — betting state",
            "Celery Beat (code-based schedule)",
        ],
    },
    "celery": {
        "label": "Celery Worker",
        "subtitle": "Background Tasks + Periodic Jobs",
        "description": "Celery workers process background tasks: fetching fixtures and standings from football-data.org, generating house odds from standings data, and settling bets when matches finish. Celery Beat schedules periodic polling tasks.",
        "tech": [
            "Celery 5.x",
            "Celery Beat",
            "celery[redis]",
            "httpx (async HTTP)",
        ],
        "pages": [
            "fetch_fixtures — daily at 3am UTC",
            "fetch_standings — midweek + 3h on matchdays",
            "generate_odds — every 10 minutes",
            "fetch_live_scores — every 5m on matchdays",
            "settle_bets — triggered on match completion",
        ],
    },
}

FLOW_PATHS = {
    "http": {
        "label": "HTTP Request",
        "description": "User clicks a link or HTMX fires a request. Django view processes it, queries PostgreSQL via ORM, renders a template (full page or partial), and returns HTML.",
        "steps": ["Browser", "Django", "PostgreSQL", "Django", "Browser"],
    },
    "websocket": {
        "label": "WebSocket",
        "description": "Browser opens a WebSocket to Daphne. When a Celery task detects a score change, it pushes a message through Redis channel layer. Daphne's consumer broadcasts the HTML update to all connected clients.",
        "steps": ["Browser", "Daphne/Channels", "Redis", "Daphne/Channels", "Browser"],
    },
    "celery": {
        "label": "Celery Task",
        "description": "Celery Beat triggers a periodic task. The worker fetches data from an external API, saves to PostgreSQL, and optionally pushes a WebSocket update through the Redis channel layer.",
        "steps": [
            "Celery Worker",
            "External API",
            "PostgreSQL",
            "Redis",
            "Daphne/Channels",
            "Browser",
        ],
    },
}


class HomeView(TemplateView):
    template_name = "epl_website/home.html"


class HowItWorksView(TemplateView):
    template_name = "epl_website/how_it_works.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["components"] = ARCHITECTURE_COMPONENTS
        context["flows"] = FLOW_PATHS
        return context


class ComponentDetailView(View):
    def get(self, request):
        name = request.GET.get("name", "")
        component = ARCHITECTURE_COMPONENTS.get(name)
        if not component:
            raise Http404
        return render(
            request,
            "epl_website/partials/component_detail.html",
            {
                "name": name,
                "component": component,
            },
        )


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("epl_matches:dashboard")


class ThemeToggleView(View):
    def post(self, request):
        requested_theme = request.POST.get("theme")
        theme = normalize_theme(requested_theme)

        if requested_theme is None:
            theme = "light" if get_theme(request) == "dark" else "dark"

        request.session[THEME_SESSION_KEY] = theme

        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if not next_url or not url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = reverse("epl_matches:dashboard")

        return redirect(next_url)


class AccountView(LoginRequiredMixin, View):
    def _partial_context(self, form, save_success=False):
        """Minimal context for HTMX partial responses — no extra DB queries."""
        return _settings_card_context(
            self.request.user,
            display_name_form=form,
            account_save_success=save_success,
        )

    def _build_context(
        self,
        form=None,
        save_success=False,
        currency_form=None,
        currency_save_success=False,
    ):
        user = self.request.user
        masked = mask_email(user.email)

        # Balance
        try:
            balance = user.balance.balance
        except UserBalance.DoesNotExist:
            balance = None

        # Stats
        try:
            stats = user.stats
        except UserStats.DoesNotExist:
            stats = None

        # Badges
        earned_map = {
            ub.badge_id: ub.earned_at
            for ub in UserBadge.objects.filter(user=user).select_related("badge")
        }
        all_badges = []
        for badge in Badge.objects.all():
            badge.earned = earned_map.get(badge.pk)
            all_badges.append(badge)

        # Avatar picker data
        avatar_frames = get_unlocked_frames(user)
        avatar_teams = list(
            Team.objects.exclude(crest_url="")
            .order_by("short_name")
            .values("short_name", "crest_url")
        )

        return {
            "display_name_form": form or DisplayNameForm(instance=user),
            "currency_form": currency_form or CurrencyForm(instance=user),
            "account_masked_email": masked,
            "account_public_identity": get_public_identity(user),
            "account_save_success": save_success,
            "currency_save_success": currency_save_success,
            "user_rank": get_user_rank(user),
            "balance": balance,
            "stats": stats,
            "all_badges": all_badges,
            "avatar_icons": AVATAR_ICONS,
            "avatar_colors": AVATAR_COLORS,
            "avatar_frames": avatar_frames,
            "avatar_teams": avatar_teams,
        }

    def get(self, request):
        return render(request, "epl_website/account.html", self._build_context())

    def post(self, request):
        form = DisplayNameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            fresh_form = DisplayNameForm(instance=request.user)
            if request.htmx:
                return render(
                    request,
                    "epl_website/partials/account_settings_card.html",
                    self._partial_context(fresh_form, save_success=True),
                )
            return render(
                request,
                "epl_website/account.html",
                self._build_context(fresh_form, save_success=True),
            )

        if request.htmx:
            return render(
                request,
                "epl_website/partials/account_settings_card.html",
                self._partial_context(form),
                status=422,
            )
        return render(
            request,
            "epl_website/account.html",
            self._build_context(form=form),
            status=422,
        )


def _settings_card_context(user, **overrides):
    """Shared context for the combined account settings card partial."""
    ctx = {
        "display_name_form": overrides.get(
            "display_name_form", DisplayNameForm(instance=user)
        ),
        "currency_form": overrides.get("currency_form", CurrencyForm(instance=user)),
        "account_masked_email": mask_email(user.email),
        "account_public_identity": get_public_identity(user),
        "account_save_success": overrides.get("account_save_success", False),
        "currency_save_success": overrides.get("currency_save_success", False),
    }
    return ctx


class CurrencyUpdateView(LoginRequiredMixin, View):
    def post(self, request):
        form = CurrencyForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            fresh_form = CurrencyForm(instance=request.user)
            if request.htmx:
                return render(
                    request,
                    "epl_website/partials/account_settings_card.html",
                    _settings_card_context(
                        request.user,
                        currency_form=fresh_form,
                        currency_save_success=True,
                    ),
                )
            return redirect("epl_website:account")

        if request.htmx:
            return render(
                request,
                "epl_website/partials/account_settings_card.html",
                _settings_card_context(request.user, currency_form=form),
                status=422,
            )
        return redirect("epl_website:account")


def get_avatar_teams():
    return list(
        Team.objects.exclude(crest_url="")
        .order_by("short_name")
        .values(
            "short_name",
            "crest_url",
        )
    )


class AvatarUpdateView(LoginRequiredMixin, View):
    def _picker_context(self, user, extra=None):
        ctx = {
            "avatar_icons": AVATAR_ICONS,
            "avatar_colors": AVATAR_COLORS,
            "avatar_frames": get_unlocked_frames(user),
            "avatar_teams": get_avatar_teams(),
        }
        if extra:
            ctx.update(extra)
        return ctx

    def post(self, request):
        form = AvatarForm(request.POST, user=request.user)
        if form.is_valid():
            crest_url = form.cleaned_data["avatar_crest_url"]
            request.user.avatar_crest_url = crest_url
            request.user.avatar_icon = form.cleaned_data["avatar_icon"]
            request.user.avatar_bg = form.cleaned_data["avatar_bg"]
            request.user.avatar_frame = form.cleaned_data["avatar_frame"]
            request.user.save(
                update_fields=[
                    "avatar_icon",
                    "avatar_bg",
                    "avatar_frame",
                    "avatar_crest_url",
                ]
            )
            if request.htmx:
                return render(
                    request,
                    "epl_website/partials/avatar_settings_card.html",
                    self._picker_context(request.user, {"avatar_save_success": True}),
                )
            return redirect("epl_website:account")

        if request.htmx:
            return render(
                request,
                "epl_website/partials/avatar_settings_card.html",
                self._picker_context(request.user),
                status=422,
            )
        return redirect("epl_website:account")


# ---------------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------------

ADMIN_PAGE_SIZE = 5
ADMIN_MAX_OFFSET = 500


class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class AdminDashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = "epl_website/admin_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        User = get_user_model()
        ctx["total_users"] = User.objects.count()
        ctx["active_bets"] = BetSlip.objects.filter(status="PENDING").count()
        ctx["active_parlays"] = Parlay.objects.filter(status="PENDING").count()
        ctx["total_comments"] = Comment.objects.filter(is_deleted=False).count()
        ctx["total_bets_all_time"] = BetSlip.objects.count() + Parlay.objects.count()
        ctx["total_in_play"] = (
            BetSlip.objects.filter(status="PENDING").aggregate(total=Sum("stake"))[
                "total"
            ]
            or 0
        )
        ctx["queued_events"] = ActivityEvent.objects.filter(
            broadcast_at__isnull=True
        ).count()
        return ctx


def _parse_offset(request):
    try:
        return min(ADMIN_MAX_OFFSET, max(0, int(request.GET.get("offset", 0))))
    except (TypeError, ValueError):
        return 0


def _paginated_response(request, items, total, offset, list_tpl, page_tpl):
    has_more = (offset + ADMIN_PAGE_SIZE) < total
    ctx = {
        "items": items,
        "has_more": has_more,
        "next_offset": offset + ADMIN_PAGE_SIZE,
        "request": request,
    }
    if offset > 0:
        html = render_to_string(page_tpl, ctx, request=request)
    else:
        html = render_to_string(list_tpl, ctx, request=request)
    return HttpResponse(html)


def _merged_querysets(qs_a, qs_b, offset, page_size):
    """Merge two querysets ordered by -created_at using heapq, with offset pagination."""
    # Fetch enough from each to cover offset + page_size
    limit = offset + page_size
    a_items = list(qs_a[:limit])
    b_items = list(qs_b[:limit])
    merged = list(merge(a_items, b_items, key=attrgetter("created_at"), reverse=True))
    return merged[offset : offset + page_size]


class AdminBetsPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        offset = _parse_offset(request)
        bets_qs = BetSlip.objects.select_related(
            "user", "match__home_team", "match__away_team"
        ).order_by("-created_at")
        parlays_qs = (
            Parlay.objects.select_related("user")
            .prefetch_related("legs__match__home_team", "legs__match__away_team")
            .order_by("-created_at")
        )
        items = _merged_querysets(bets_qs, parlays_qs, offset, ADMIN_PAGE_SIZE)
        total = BetSlip.objects.count() + Parlay.objects.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "epl_website/partials/admin_bets_list.html",
            "epl_website/partials/admin_bets_page.html",
        )


class AdminCommentsPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        offset = _parse_offset(request)
        qs = (
            Comment.objects.filter(is_deleted=False)
            .select_related("user", "match__home_team", "match__away_team")
            .order_by("-created_at")
        )
        items = list(qs[offset : offset + ADMIN_PAGE_SIZE])
        total = qs.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "epl_website/partials/admin_comments_list.html",
            "epl_website/partials/admin_comments_page.html",
        )


class AdminUsersPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        User = get_user_model()
        offset = _parse_offset(request)
        qs = User.objects.filter(is_bot=False).order_by("-date_joined")
        items = list(qs[offset : offset + ADMIN_PAGE_SIZE])
        total = qs.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "epl_website/partials/admin_users_list.html",
            "epl_website/partials/admin_users_page.html",
        )


class AdminActivityQueuePartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        offset = _parse_offset(request)
        qs = ActivityEvent.objects.filter(broadcast_at__isnull=True).order_by(
            "created_at"
        )
        items = list(qs[offset : offset + ADMIN_PAGE_SIZE])
        total = qs.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "epl_website/partials/admin_activity_queue_list.html",
            "epl_website/partials/admin_activity_queue_page.html",
        )
