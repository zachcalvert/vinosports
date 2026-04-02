from decimal import Decimal

from django import forms

from nfl.betting.models import BetSlip


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
        max_value=Decimal("100000000.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "themed-input themed-input-mono themed-input-right",
                "placeholder": "0.00",
                "step": "0.50",
                "min": "0.50",
                "max": "100000000.00",
            }
        ),
    )


class PlaceParlayForm(forms.Form):
    stake = forms.DecimalField(
        min_value=Decimal("0.50"),
        max_value=Decimal("100000000.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "themed-input themed-input-mono themed-input-right",
                "placeholder": "0.00",
                "step": "0.50",
                "min": "0.50",
                "max": "100000000.00",
                "id": "parlay-stake-input",
            }
        ),
    )


class PlaceFuturesBetForm(forms.Form):
    stake = forms.DecimalField(
        min_value=Decimal("0.50"),
        max_value=Decimal("100000000.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "themed-input themed-input-mono themed-input-right",
                "placeholder": "0.00",
                "step": "0.50",
                "min": "0.50",
                "max": "100000000.00",
            }
        ),
    )
