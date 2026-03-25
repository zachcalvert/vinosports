class LeagueMiddleware:
    """Set request.league based on URL path prefix.

    Used by league-specific context processors to short-circuit
    when serving pages for a different league (or the hub).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path.startswith("/epl/"):
            request.league = "epl"
        elif path.startswith("/nba/"):
            request.league = "nba"
        else:
            request.league = None
        return self.get_response(request)
