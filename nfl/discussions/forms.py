from django import forms


class CommentForm(forms.Form):
    body = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "themed-input",
                "placeholder": "Share your thoughts...",
                "rows": 3,
                "maxlength": "1000",
            }
        ),
    )
