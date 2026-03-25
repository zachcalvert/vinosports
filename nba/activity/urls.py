from django.urls import path

from nba.activity.views import ToggleToastsView

app_name = "nba_activity"

urlpatterns = [
    path("toggle-toasts/", ToggleToastsView.as_view(), name="toggle_toasts"),
]
