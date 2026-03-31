from django.urls import path

from nfl.activity.views import ToggleToastsView

app_name = "nfl_activity"

urlpatterns = [
    path("toggle-toasts/", ToggleToastsView.as_view(), name="toggle_toasts"),
]
