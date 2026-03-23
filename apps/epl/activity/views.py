from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View


class ToggleToastsView(LoginRequiredMixin, View):
    def post(self, request):
        show = "show_activity_toasts" in request.POST
        request.user.show_activity_toasts = show
        request.user.save(update_fields=["show_activity_toasts"])

        if getattr(request, "htmx", False):
            from website.views import _settings_card_context

            return render(
                request,
                "website/partials/account_settings_card.html",
                _settings_card_context(request.user),
            )
        return redirect("website:account")
