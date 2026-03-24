from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from vinosports.rewards.models import RewardDistribution


class DismissRewardView(LoginRequiredMixin, View):
    def post(self, request, pk):
        RewardDistribution.objects.filter(pk=pk, user=request.user).update(seen=True)
        return HttpResponse("")
