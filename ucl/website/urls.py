from django.urls import path

from ucl.website.views import HowItWorksView

app_name = "ucl_website"

urlpatterns = [
    path("how-it-works/", HowItWorksView.as_view(), name="how_it_works"),
]
