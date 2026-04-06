from django import forms

from worldcup.discussions.models import Comment


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Share your thoughts...",
                    "maxlength": 1000,
                }
            ),
        }
