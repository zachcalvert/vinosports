from django.urls import path

from . import views

app_name = "activity"

urlpatterns = [
    path("toggle-toasts/", views.ToggleToastsView.as_view(), name="toggle_toasts"),
]
