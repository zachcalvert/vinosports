def activity_toasts(request):
    """Provide ``show_activity_toasts`` flag for base template."""
    if getattr(request, "league", None) != "nba":
        return {}
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return {"show_activity_toasts": user.show_activity_toasts}
    return {"show_activity_toasts": True}
