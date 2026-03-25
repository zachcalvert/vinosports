from vinosports.rewards.models import RewardDistribution


def unseen_rewards(request):
    if getattr(request, "league", None) != "epl":
        return {"unseen_rewards": []}
    if not request.user.is_authenticated:
        return {"unseen_rewards": []}

    distributions = (
        RewardDistribution.objects.filter(user=request.user, seen=False)
        .select_related("reward")
        .order_by("-created_at")[:5]
    )

    return {"unseen_rewards": list(distributions)}
