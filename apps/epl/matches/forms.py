from django import forms

from matches.models import MatchNotes


class MatchNotesForm(forms.ModelForm):
    class Meta:
        model = MatchNotes
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={
                "rows": 8,
                "placeholder": "Key moments, goalscorers, drama, red cards, VAR incidents...",
                "class": (
                    "w-full bg-dark border border-gray-700 rounded-md px-3 py-2 "
                    "text-sm text-white placeholder-gray-500 focus:border-accent "
                    "focus:outline-none focus:ring-1 focus:ring-accent"
                ),
            }),
        }
