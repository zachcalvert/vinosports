import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def celery_eager(settings):
    """Force all Celery tasks to run synchronously in tests."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Django cache between tests to avoid stale leaderboard data."""
    cache.clear()
    yield
    cache.clear()
