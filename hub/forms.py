from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class ProfileImageForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("profile_image",)
        widgets = {
            "profile_image": forms.ClearableFileInput(
                attrs={"class": "themed-input themed-input-sm", "accept": "image/*"}
            )
        }


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


class SignupForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "themed-input",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )
    )
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(
            attrs={
                "class": "themed-input",
                "placeholder": "Min. 8 characters",
                "autocomplete": "new-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "themed-input",
                "placeholder": "Confirm password",
                "autocomplete": "new-password",
            }
        ),
    )
    promo_code = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "themed-input",
                "placeholder": "Enter a promo code (optional)",
                "autocomplete": "off",
            }
        ),
    )

    def clean_promo_code(self):
        code = self.cleaned_data.get("promo_code", "").strip()
        if code and " " in code:
            raise forms.ValidationError("Promo code must not contain spaces.")
        return code

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        pw2 = cleaned.get("password_confirm")
        if pw and pw2 and pw != pw2:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "themed-input",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "themed-input",
                "placeholder": "Password",
                "autocomplete": "current-password",
            }
        ),
    )
