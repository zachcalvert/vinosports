from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model

from nba.betting.models import BetSlip

User = get_user_model()


class PlaceBetForm(forms.Form):
    market = forms.ChoiceField(
        choices=BetSlip.Market.choices,
        widget=forms.HiddenInput(),
    )
    selection = forms.ChoiceField(
        choices=BetSlip.Selection.choices,
        widget=forms.HiddenInput(),
    )
    odds = forms.IntegerField(widget=forms.HiddenInput())
    line = forms.FloatField(required=False, widget=forms.HiddenInput())
    stake = forms.DecimalField(
        min_value=Decimal("0.50"),
        max_value=Decimal("10000.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "themed-input themed-input-mono themed-input-right",
                "placeholder": "0.00",
                "step": "0.50",
                "min": "0.50",
                "max": "10000.00",
            }
        ),
    )


class PlaceParlayForm(forms.Form):
    stake = forms.DecimalField(
        min_value=Decimal("0.50"),
        max_value=Decimal("10000.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "themed-input themed-input-mono themed-input-right",
                "placeholder": "0.00",
                "step": "0.50",
                "min": "0.50",
                "max": "10000.00",
                "id": "parlay-stake-input",
            }
        ),
    )


class DisplayNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("display_name",)
        widgets = {
            "display_name": forms.TextInput(
                attrs={
                    "class": "themed-input themed-input-sm",
                    "placeholder": "Enter a display name",
                    "maxlength": "50",
                }
            )
        }

    def clean_display_name(self):
        display_name = (self.cleaned_data.get("display_name") or "").strip()
        if not display_name:
            return None

        duplicate_exists = (
            User.objects.exclude(pk=self.instance.pk)
            .filter(display_name__iexact=display_name)
            .exists()
        )
        if duplicate_exists:
            raise forms.ValidationError("Display name already taken.")

        return display_name


class CurrencyForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("currency",)
        widgets = {
            "currency": forms.Select(attrs={"class": "themed-input themed-input-sm"})
        }
