from django.urls import path

from challenges.views import (
    ActiveChallengesPartial,
    ChallengesPageView,
    ChallengeWidgetPartial,
    CompletedChallengesPartial,
    UpcomingChallengesPartial,
)

app_name = "challenges"

urlpatterns = [
    path("challenges/", ChallengesPageView.as_view(), name="challenges"),
    path(
        "challenges/active/", ActiveChallengesPartial.as_view(), name="active_partial"
    ),
    path(
        "challenges/completed/",
        CompletedChallengesPartial.as_view(),
        name="completed_partial",
    ),
    path(
        "challenges/upcoming/",
        UpcomingChallengesPartial.as_view(),
        name="upcoming_partial",
    ),
    path("challenges/widget/", ChallengeWidgetPartial.as_view(), name="widget_partial"),
]
