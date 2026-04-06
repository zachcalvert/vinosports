"""World Cup website views — account, how-it-works, theme toggle."""

from django.views.generic import TemplateView


class HowItWorksView(TemplateView):
    template_name = "worldcup_website/how_it_works.html"
