from django import forms

from nba.games.models import GameNotes


class GameNotesForm(forms.ModelForm):
    class Meta:
        model = GameNotes
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 8,
                    "placeholder": "Key plays, clutch moments, controversial calls, standout performances...",
                    "class": (
                        "w-full bg-dark border border-gray-700 rounded-md px-3 py-2 "
                        "text-sm text-white placeholder-gray-500 focus:border-accent "
                        "focus:outline-none focus:ring-1 focus:ring-accent"
                    ),
                }
            ),
        }
