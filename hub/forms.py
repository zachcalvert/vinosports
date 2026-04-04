from django import forms
from django.contrib.auth import get_user_model

from vinosports.bots.models import BotProfile

User = get_user_model()


_input = "themed-input themed-input-sm"
_textarea = "themed-input w-full"
_select = "themed-input themed-input-sm"
_checkbox = "h-4 w-4 rounded border-outline accent-primary"


class BotProfileForm(forms.ModelForm):
    """Form for creating or editing a user's bot profile."""

    class Meta:
        model = BotProfile
        fields = (
            "persona_prompt",
            "tagline",
            "avatar_icon",
            "avatar_bg",
            "portrait_url",
            "strategy_type",
            "risk_multiplier",
            "max_daily_bets",
            "active_in_epl",
            "active_in_nba",
            "active_in_nfl",
            "epl_team_tla",
            "nba_team_abbr",
            "nfl_team_abbr",
        )
        widgets = {
            "persona_prompt": forms.Textarea(
                attrs={
                    "class": _textarea,
                    "rows": 5,
                    "placeholder": (
                        "Describe your bot's personality. "
                        "Do NOT include team references — those are injected at runtime."
                    ),
                }
            ),
            "tagline": forms.TextInput(
                attrs={"class": _input, "placeholder": "A short public-facing quote"}
            ),
            "avatar_icon": forms.TextInput(
                attrs={"class": _input, "placeholder": "e.g. robot"}
            ),
            "avatar_bg": forms.TextInput(
                attrs={"class": _input, "placeholder": "#374151", "type": "color"}
            ),
            "portrait_url": forms.URLInput(
                attrs={"class": _input, "placeholder": "https://…"}
            ),
            "strategy_type": forms.Select(attrs={"class": _select}),
            "risk_multiplier": forms.NumberInput(
                attrs={"class": _input, "step": "0.1", "min": "0.1", "max": "10"}
            ),
            "max_daily_bets": forms.NumberInput(
                attrs={"class": _input, "min": "1", "max": "50"}
            ),
            "active_in_epl": forms.CheckboxInput(attrs={"class": _checkbox}),
            "active_in_nba": forms.CheckboxInput(attrs={"class": _checkbox}),
            "active_in_nfl": forms.CheckboxInput(attrs={"class": _checkbox}),
            "epl_team_tla": forms.TextInput(
                attrs={"class": _input, "placeholder": "e.g. ARS", "maxlength": "5"}
            ),
            "nba_team_abbr": forms.TextInput(
                attrs={"class": _input, "placeholder": "e.g. GSW", "maxlength": "5"}
            ),
            "nfl_team_abbr": forms.TextInput(
                attrs={"class": _input, "placeholder": "e.g. KC", "maxlength": "5"}
            ),
        }


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
