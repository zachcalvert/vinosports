from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View


class ToggleToastsView(LoginRequiredMixin, View):
    def post(self, request):
        show = "show_activity_toasts" in request.POST
        request.user.show_activity_toasts = show
        request.user.save(update_fields=["show_activity_toasts"])
        return redirect("nfl_website:account")
