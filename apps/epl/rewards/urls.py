from django.urls import path

from .views import DismissRewardView

app_name = "rewards"

urlpatterns = [
    path("<int:pk>/dismiss/", DismissRewardView.as_view(), name="dismiss"),
]
