from django import forms


class CommentForm(forms.Form):
    body = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "themed-input w-full text-sm",
                "rows": 3,
                "placeholder": "Join the discussion...",
                "maxlength": "1000",
            }
        ),
    )
