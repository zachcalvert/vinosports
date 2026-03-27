from django import forms

from epl.matches.models import Team
from epl.users.avatars import AVATAR_COLORS, AVATAR_ICONS, get_frame_by_slug
from vinosports.betting.models import UserBadge


class AvatarForm(forms.Form):
    avatar_icon = forms.ChoiceField(choices=[(i, i) for i in AVATAR_ICONS])
    avatar_bg = forms.ChoiceField(choices=[(c, c) for c in AVATAR_COLORS])
    avatar_frame = forms.CharField(required=False)
    avatar_crest_url = forms.URLField(required=False, assume_scheme="https")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_avatar_crest_url(self):
        value = self.cleaned_data.get("avatar_crest_url", "").strip()
        if not value:
            return ""
        # Check both crest_url and crest_image (via the crest property)
        for team in Team.objects.exclude(crest_url="", crest_image=""):
            if team.crest == value:
                return value
        raise forms.ValidationError("Invalid crest URL.")

    def clean_avatar_frame(self):
        slug = self.cleaned_data.get("avatar_frame", "").strip()
        if not slug:
            return ""
        frame = get_frame_by_slug(slug)
        if not frame:
            raise forms.ValidationError("Invalid frame.")
        if not UserBadge.objects.filter(
            user=self.user, badge__slug=frame["required_badge_slug"]
        ).exists():
            raise forms.ValidationError("You haven't unlocked this frame yet.")
        return slug
