from worldcup.matches.models import Match


def live_matches(request):
    if getattr(request, "league", None) != "worldcup":
        return {}
    live = Match.objects.filter(
        status__in=[
            Match.Status.IN_PLAY,
            Match.Status.PAUSED,
            Match.Status.EXTRA_TIME,
            Match.Status.PENALTY_SHOOTOUT,
        ]
    ).select_related("home_team", "away_team", "stage")
    return {"wc_live_matches": live}
