from django.urls import path

from worldcup.website.views import HowItWorksView

app_name = "worldcup_website"

urlpatterns = [
    path("how-it-works/", HowItWorksView.as_view(), name="how_it_works"),
]
