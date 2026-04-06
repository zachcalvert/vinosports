from django.views.generic import ListView

from worldcup.activity.models import ActivityEvent


class ActivityFeedView(ListView):
    model = ActivityEvent
    template_name = "worldcup_activity/feed.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        return ActivityEvent.objects.filter(broadcast_at__isnull=False).order_by(
            "-broadcast_at"
        )
