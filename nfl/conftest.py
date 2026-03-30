import pytest


@pytest.fixture(autouse=True)
def celery_eager(settings):
    """Force all Celery tasks to run synchronously in tests."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture
def api_client():
    from django.test import Client

    return Client()
