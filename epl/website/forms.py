from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


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
