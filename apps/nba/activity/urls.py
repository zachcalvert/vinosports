from django.urls import path

from activity.views import ToggleToastsView

app_name = "activity"

urlpatterns = [
    path("toggle-toasts/", ToggleToastsView.as_view(), name="toggle_toasts"),
]
