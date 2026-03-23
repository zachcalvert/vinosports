import re

from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
)

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
