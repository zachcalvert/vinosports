from django.urls import path

from worldcup.activity.views import ActivityFeedView

app_name = "worldcup_activity"

urlpatterns = [
    path("", ActivityFeedView.as_view(), name="feed"),
]
