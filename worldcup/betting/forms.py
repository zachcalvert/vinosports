from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator

from worldcup.betting.models import BetSlip


class PlaceBetForm(forms.Form):
    match_id = forms.IntegerField(widget=forms.HiddenInput)
    selection = forms.ChoiceField(choices=BetSlip.Selection.choices)
    odds = forms.DecimalField(max_digits=6, decimal_places=2, widget=forms.HiddenInput)
    stake = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.50"))],
    )


class PlaceParlayForm(forms.Form):
    stake = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.50"))],
    )
