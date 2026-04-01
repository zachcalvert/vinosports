import pytest


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    """Use MD5 instead of PBKDF2 — tests don't need real password security."""
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]
