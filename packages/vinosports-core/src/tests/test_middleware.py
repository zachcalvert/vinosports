"""Tests for vinosports middleware — BotScannerBlockMiddleware and CanonicalHostMiddleware."""

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from vinosports.middleware import BotScannerBlockMiddleware, CanonicalHostMiddleware


@pytest.fixture
def rf():
    return RequestFactory()


def _make_response(request):
    """Dummy get_response."""
    return HttpResponse("OK")


class TestBotScannerBlockMiddleware:
    def test_blocks_wp_admin(self, rf):
        mw = BotScannerBlockMiddleware(_make_response)
        request = rf.get("/wp-admin/")
        response = mw(request)
        assert response.status_code == 403

    def test_blocks_env_file(self, rf):
        mw = BotScannerBlockMiddleware(_make_response)
        request = rf.get("/.env")
        response = mw(request)
        assert response.status_code == 403

    def test_blocks_php_extension(self, rf):
        mw = BotScannerBlockMiddleware(_make_response)
        request = rf.get("/some/page.php")
        response = mw(request)
        assert response.status_code == 403

    def test_allows_normal_paths(self, rf):
        mw = BotScannerBlockMiddleware(_make_response)
        request = rf.get("/nba/dashboard/")
        response = mw(request)
        assert response.status_code == 200

    def test_allows_root(self, rf):
        mw = BotScannerBlockMiddleware(_make_response)
        request = rf.get("/")
        response = mw(request)
        assert response.status_code == 200


class TestCanonicalHostMiddleware:
    @override_settings(DEBUG=False, CANONICAL_HOST="vinosports.com")
    def test_redirects_www_get(self, rf):
        mw = CanonicalHostMiddleware(_make_response)
        request = rf.get("/nba/")
        request.META["HTTP_HOST"] = "www.vinosports.com"
        response = mw(request)
        assert response.status_code == 301
        assert response["Location"] == "https://vinosports.com/nba/"

    @override_settings(DEBUG=False, CANONICAL_HOST="vinosports.com")
    def test_redirects_www_post_as_302(self, rf):
        mw = CanonicalHostMiddleware(_make_response)
        request = rf.post("/submit/")
        request.META["HTTP_HOST"] = "www.vinosports.com"
        response = mw(request)
        assert response.status_code == 302

    @override_settings(DEBUG=False, CANONICAL_HOST="vinosports.com")
    def test_no_redirect_for_canonical(self, rf):
        mw = CanonicalHostMiddleware(_make_response)
        request = rf.get("/")
        request.META["HTTP_HOST"] = "vinosports.com"
        response = mw(request)
        assert response.status_code == 200

    @override_settings(DEBUG=True, CANONICAL_HOST="vinosports.com")
    def test_no_redirect_in_debug(self, rf):
        mw = CanonicalHostMiddleware(_make_response)
        request = rf.get("/")
        request.META["HTTP_HOST"] = "www.vinosports.com"
        response = mw(request)
        assert response.status_code == 200
