from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


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
