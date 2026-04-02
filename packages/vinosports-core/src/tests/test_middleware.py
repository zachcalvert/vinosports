"""Tests for vinosports middleware — BotScannerBlockMiddleware, RateLimitMiddleware, and CanonicalHostMiddleware."""

from unittest.mock import MagicMock

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from vinosports.middleware import (
    BotScannerBlockMiddleware,
    CanonicalHostMiddleware,
    RateLimitMiddleware,
)


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


class TestRateLimitMiddleware:
    """Each test uses a unique fake IP to avoid cross-test cache pollution."""

    @staticmethod
    def _next_ip():
        import uuid

        return f"test-{uuid.uuid4().hex[:12]}"

    def _make_mw(self):
        mw = RateLimitMiddleware(_make_response)
        mw.max_requests = 3
        mw.window = 60
        return mw

    def _anon_request(self, rf, path="/nba/games/schedule/", ip=None):
        request = rf.get(path, HTTP_X_FORWARDED_FOR=ip or "127.0.0.1")
        request.user = MagicMock(is_authenticated=False)
        return request

    def test_allows_non_league_paths(self, rf):
        mw = self._make_mw()
        request = rf.get("/about/")
        request.user = MagicMock(is_authenticated=False)
        response = mw(request)
        assert response.status_code == 200

    def test_allows_authenticated_users(self, rf):
        mw = self._make_mw()
        for _ in range(5):
            request = rf.get("/nba/games/schedule/")
            request.user = MagicMock(is_authenticated=True)
            response = mw(request)
            assert response.status_code == 200

    @pytest.mark.django_db
    def test_blocks_anonymous_after_threshold(self, rf):
        ip = self._next_ip()
        mw = self._make_mw()
        for i in range(3):
            response = mw(self._anon_request(rf, ip=ip))
            assert response.status_code == 200, f"Request {i + 1} should be allowed"

        response = mw(self._anon_request(rf, ip=ip))
        assert response.status_code == 429

    @pytest.mark.django_db
    @pytest.mark.parametrize("prefix", ["/epl/", "/nba/", "/nfl/"])
    def test_rate_limits_league_prefix(self, rf, prefix):
        ip = self._next_ip()
        mw = self._make_mw()
        for _ in range(3):
            mw(self._anon_request(rf, path=f"{prefix}schedule/", ip=ip))

        response = mw(self._anon_request(rf, path=f"{prefix}schedule/", ip=ip))
        assert response.status_code == 429, f"{prefix} should be rate limited"

    @pytest.mark.django_db
    def test_uses_x_forwarded_for(self, rf):
        ip = self._next_ip()
        mw = self._make_mw()
        for _ in range(3):
            mw(self._anon_request(rf, ip=ip))

        response = mw(self._anon_request(rf, ip=ip))
        assert response.status_code == 429

        # Different IP should still be allowed
        other_ip = self._next_ip()
        response = mw(self._anon_request(rf, ip=other_ip))
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
