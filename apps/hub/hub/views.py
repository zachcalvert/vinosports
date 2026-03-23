from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from vinosports.betting.models import UserBalance

from .forms import CurrencyForm, DisplayNameForm


class HomeView(TemplateView):
    template_name = "hub/home.html"


def _account_context(
    user,
    display_name_form=None,
    currency_form=None,
    save_success=False,
    currency_save_success=False,
):
    try:
        balance = user.balance.balance
    except UserBalance.DoesNotExist:
        balance = None

    masked_email = user.email.split("@")[0][:3] + "***@" + user.email.split("@")[1]

    return {
        "display_name_form": display_name_form or DisplayNameForm(instance=user),
        "currency_form": currency_form or CurrencyForm(instance=user),
        "balance": balance,
        "account_masked_email": masked_email,
        "save_success": save_success,
        "currency_save_success": currency_save_success,
    }


class AccountView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "hub/account.html", _account_context(request.user))

    def post(self, request):
        form = DisplayNameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            fresh_form = DisplayNameForm(instance=request.user)
            return render(
                request,
                "hub/account.html",
                _account_context(
                    request.user, display_name_form=fresh_form, save_success=True
                ),
            )
        return render(
            request,
            "hub/account.html",
            _account_context(request.user, display_name_form=form),
        )


class CurrencyUpdateView(LoginRequiredMixin, View):
    def post(self, request):
        form = CurrencyForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return render(
                request,
                "hub/account.html",
                _account_context(
                    request.user,
                    currency_form=CurrencyForm(instance=request.user),
                    currency_save_success=True,
                ),
            )
        return redirect("hub:account")
