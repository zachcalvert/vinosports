import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from vinosports.challenges.models import Challenge, UserChallenge

logger = logging.getLogger(__name__)


def _get_user_challenges(user, status_filter=None):
    """Return UserChallenge queryset for a user with optional status filter."""
    qs = (
        UserChallenge.objects.filter(user=user)
        .select_related("challenge__template")
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    return qs


def _ensure_enrollment(user):
    """Lazily enroll user into all active challenges they haven't joined."""
    active_challenges = Challenge.objects.filter(
        status=Challenge.Status.ACTIVE
    ).select_related("template")

    existing_ids = set(
        UserChallenge.objects.filter(
            user=user, challenge__in=active_challenges
        ).values_list("challenge_id", flat=True)
    )

    new_ucs = []
    for challenge in active_challenges:
        if challenge.pk not in existing_ids:
            new_ucs.append(
                UserChallenge(
                    user=user,
                    challenge=challenge,
                    target=challenge.target,
                )
            )
    if new_ucs:
        UserChallenge.objects.bulk_create(new_ucs, ignore_conflicts=True)


class ChallengesPageView(LoginRequiredMixin, TemplateView):
    template_name = "challenges/challenges_page.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        _ensure_enrollment(user)

        tab = self.request.GET.get("tab", "active")
        ctx["active_tab"] = tab

        if tab == "active":
            ctx["challenges"] = _get_user_challenges(
                user, UserChallenge.Status.IN_PROGRESS
            )
        elif tab == "completed":
            ctx["challenges"] = _get_user_challenges(
                user, UserChallenge.Status.COMPLETED
            )
        elif tab == "upcoming":
            ctx["upcoming_challenges"] = (
                Challenge.objects.filter(status=Challenge.Status.UPCOMING)
                .select_related("template")
                .order_by("starts_at")
            )
        else:
            ctx["challenges"] = _get_user_challenges(
                user, UserChallenge.Status.IN_PROGRESS
            )

        return ctx


class ActiveChallengesPartial(LoginRequiredMixin, TemplateView):
    template_name = "challenges/partials/challenge_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        _ensure_enrollment(self.request.user)
        ctx["challenges"] = _get_user_challenges(
            self.request.user, UserChallenge.Status.IN_PROGRESS
        )
        ctx["active_tab"] = "active"
        return ctx


class CompletedChallengesPartial(LoginRequiredMixin, TemplateView):
    template_name = "challenges/partials/challenge_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["challenges"] = _get_user_challenges(
            self.request.user, UserChallenge.Status.COMPLETED
        )
        ctx["active_tab"] = "completed"
        return ctx


class UpcomingChallengesPartial(LoginRequiredMixin, TemplateView):
    template_name = "challenges/partials/challenge_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["upcoming_challenges"] = (
            Challenge.objects.filter(status=Challenge.Status.UPCOMING)
            .select_related("template")
            .order_by("starts_at")
        )
        ctx["active_tab"] = "upcoming"
        return ctx


class ChallengeWidgetPartial(LoginRequiredMixin, TemplateView):
    template_name = "challenges/partials/challenge_widget.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        _ensure_enrollment(self.request.user)
        ctx["active_challenges"] = _get_user_challenges(
            self.request.user, UserChallenge.Status.IN_PROGRESS
        )[:3]
        return ctx
