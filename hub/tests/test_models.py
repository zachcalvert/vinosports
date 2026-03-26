"""Tests for hub.models — SiteSettings singleton."""

import pytest

from hub.models import SiteSettings

pytestmark = pytest.mark.django_db


class TestSiteSettings:
    def test_load_creates_singleton(self):
        site = SiteSettings.load()
        assert site.pk == 1
        assert site.max_users == 100

    def test_load_returns_same_instance(self):
        s1 = SiteSettings.load()
        s1.max_users = 50
        s1.save()
        s2 = SiteSettings.load()
        assert s2.max_users == 50

    def test_save_forces_pk_1(self):
        site = SiteSettings(pk=99, max_users=200)
        site.save()
        assert site.pk == 1
        assert SiteSettings.objects.count() == 1

    def test_str(self):
        assert str(SiteSettings.load()) == "Site Settings"
