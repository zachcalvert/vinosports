import logging
import re

from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
)

logger = logging.getLogger(__name__)

# Patterns that vulnerability scanners/bots probe for.
BLOCKED_PATH_PREFIXES = (
    "/wordpress/",
    "/wp-admin/",
    "/wp-content/",
    "/wp-includes/",
    "/wp-login",
    "/wp-json/",
    "/xmlrpc.php",
    "/.env",
    "/.git/",
    "/phpmyadmin",
    "/admin.php",
    "/administrator/",
    "/cgi-bin/",
    "/vendor/",
    "/telescope/",
    "/debug/",
    "/solr/",
    "/actuator/",
    "/config.php",
    "/console/",
    "/druid/",
)

BLOCKED_PATH_RE = re.compile(
    r"\.(?:php|asp|aspx|jsp|cgi)$",
    re.IGNORECASE,
)


class BotScannerBlockMiddleware:
    """Return 403 immediately for paths that only vulnerability scanners request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.lower()
        if any(
            path.startswith(p) for p in BLOCKED_PATH_PREFIXES
        ) or BLOCKED_PATH_RE.search(path):
            return HttpResponse("Forbidden", status=403)
        return self.get_response(request)


class RateLimitMiddleware:
    """Throttle anonymous requests to league pages by IP.

    Uses Django's Redis cache to track request counts per IP in a
    sliding window. Authenticated users are exempt. Returns 429 when
    the threshold is exceeded.

    Settings (with defaults):
        RATE_LIMIT_REQUESTS = 60     # max requests per window
        RATE_LIMIT_WINDOW   = 60     # window in seconds
    """

    LEAGUE_PREFIXES = ("/epl/", "/nba/", "/nfl/")

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_requests = getattr(settings, "RATE_LIMIT_REQUESTS", 60)
        self.window = getattr(settings, "RATE_LIMIT_WINDOW", 60)

    def __call__(self, request):
        # Only rate-limit league pages
        if not any(request.path.startswith(p) for p in self.LEAGUE_PREFIXES):
            return self.get_response(request)

        # Authenticated users are exempt
        if hasattr(request, "user") and request.user.is_authenticated:
            return self.get_response(request)

        ip = self._get_client_ip(request)
        cache_key = f"rl:{ip}"

        try:
            from django.core.cache import cache

            count = cache.get_or_set(cache_key, 0, timeout=self.window)
            if count >= self.max_requests:
                logger.warning(
                    "Rate limited IP %s (%d requests in %ds)", ip, count, self.window
                )
                return HttpResponse(
                    "Too Many Requests",
                    status=429,
                    headers={"Retry-After": str(self.window)},
                )
            cache.incr(cache_key)
        except Exception:
            # If Redis is down, fail open — don't block users
            pass

        return self.get_response(request)

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP, respecting X-Forwarded-For from Fly.io proxy."""
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")


class CanonicalHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical_host = getattr(settings, "CANONICAL_HOST", None)

        if not settings.DEBUG and canonical_host:
            request_host = request.get_host().split(":", 1)[0]
            if request_host == f"www.{canonical_host}":
                url = f"https://{canonical_host}{request.get_full_path()}"
                if request.method in ("GET", "HEAD"):
                    return HttpResponsePermanentRedirect(url)
                return HttpResponseRedirect(url)

        return self.get_response(request)
