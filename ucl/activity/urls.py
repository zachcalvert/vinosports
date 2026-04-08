from django.urls import path

from ucl.activity.views import ActivityFeedView

app_name = "ucl_activity"

urlpatterns = [
    path("", ActivityFeedView.as_view(), name="feed"),
]
