from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

from vinosports.challenges.models import Challenge, UserChallenge


class ChallengesPageView(LoginRequiredMixin, View):
    def get(self, request):
        active_challenges = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
        ).select_related("template")

        user_challenges = {}
        if request.user.is_authenticated:
            user_challenges = {
                uc.challenge_id: uc
                for uc in UserChallenge.objects.filter(
                    user=request.user,
                    challenge__status=Challenge.Status.ACTIVE,
                )
            }

        return render(
            request,
            "nba_challenges/challenge_list.html",
            {
                "active_challenges": active_challenges,
                "user_challenges": user_challenges,
            },
        )
