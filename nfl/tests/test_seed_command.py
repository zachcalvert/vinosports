"""Tests for the seed_nfl management command."""

import pytest
from django.core.management import call_command

from nfl.games.models import Team


@pytest.mark.django_db
class TestSeedNFLOffline:
    def test_seeds_teams_offline(self):
        call_command("seed_nfl", "--offline", "--teams-only")
        assert Team.objects.count() == 32

    def test_sets_logos(self):
        call_command("seed_nfl", "--offline", "--teams-only")
        kc = Team.objects.get(external_id=14)
        assert "espncdn.com" in kc.logo_url

    def test_team_data_correct(self):
        call_command("seed_nfl", "--offline", "--teams-only")
        kc = Team.objects.get(external_id=14)
        assert kc.name == "Kansas City Chiefs"
        assert kc.short_name == "Chiefs"
        assert kc.abbreviation == "KC"
        assert kc.conference == "AFC"
        assert kc.division == "AFC_WEST"

    def test_idempotent(self):
        call_command("seed_nfl", "--offline", "--teams-only")
        call_command("seed_nfl", "--offline", "--teams-only")
        assert Team.objects.count() == 32
