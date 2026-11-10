import pytest

from rosie.config import settings


@pytest.fixture(autouse=True)
def turnstile_off(monkeypatch):
    """Tests run with Turnstile off, whatever the local .env says; a test turns it on itself."""
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", "")
