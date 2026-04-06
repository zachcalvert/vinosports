from django import forms

from worldcup.matches.models import MatchNotes


class MatchNotesForm(forms.ModelForm):
    class Meta:
        model = MatchNotes
        fields = ["body"]
