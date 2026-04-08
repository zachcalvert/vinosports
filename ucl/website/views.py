"""UCL website views — how-it-works, theme toggle."""

from django.views.generic import TemplateView


class HowItWorksView(TemplateView):
    template_name = "ucl_website/how_it_works.html"
