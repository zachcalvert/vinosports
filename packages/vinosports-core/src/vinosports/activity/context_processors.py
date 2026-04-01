from django.utils import timezone

from vinosports.activity.models import Notification


def unread_notification_count(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}

    count = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
        expires_at__gt=timezone.now(),
    ).count()

    return {"unread_notification_count": count}
