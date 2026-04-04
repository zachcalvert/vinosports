from vinosports.core.models import GlobalKnowledge


def get_global_context():
    """Return formatted global knowledge for injection into bot prompts.

    Returns an empty string if no active headlines exist.
    """
    items = GlobalKnowledge.objects.filter(is_active=True)
    if not items:
        return ""

    lines = ["What's happening in the world right now:"]
    for item in items:
        lines.append(f"- {item.headline}")
        if item.detail.strip():
            lines.append(f"  {item.detail.strip()}")
    return "\n".join(lines)
