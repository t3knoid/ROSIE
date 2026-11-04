import httpx
import pytest

from rosie.config import Settings
from rosie import source_sync


def make_settings(**overrides):
    return Settings(_env_file=None, **overrides)


def mock_client(monkeypatch, response):
    requests = []

    def handler(request):
        requests.append(request)
        return response

    original_client = httpx.Client
    monkeypatch.setattr(
        source_sync.httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return requests


def test_sync_runs_once_per_configured_interval(tmp_path, monkeypatch):
    requests = mock_client(monkeypatch, httpx.Response(200, json={"pages": 2, "chunks": 4, "errors": []}))
    monkeypatch.setattr(source_sync.time, "time", lambda: 10000)
    state = tmp_path / "state" / "last-attempt"
    settings = make_settings(source_sync_interval_seconds=120)
    assert source_sync.sync_if_due(settings, state)
    assert not source_sync.sync_if_due(settings, state)
    monkeypatch.setattr(source_sync.time, "time", lambda: 10120)
    assert source_sync.sync_if_due(settings, state)
    assert len(requests) == 2
    assert requests[0].method == "POST"
    assert str(requests[0].url) == settings.source_sync_api_url


def test_disabled_sync_does_not_fetch_or_write_state(tmp_path, monkeypatch):
    requests = mock_client(monkeypatch, httpx.Response(500))
    state = tmp_path / "last-attempt"
    assert not source_sync.sync_if_due(make_settings(source_sync_enabled=False), state)
    assert not requests
    assert not state.exists()


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"errors": ["page unavailable"]}),
    httpx.Response(200, json={}),
    httpx.Response(503),
])
def test_failures_are_reported_and_throttled(tmp_path, monkeypatch, response):
    requests = mock_client(monkeypatch, response)
    state = tmp_path / "last-attempt"
    with pytest.raises((ValueError, httpx.HTTPStatusError)):
        source_sync.sync_if_due(make_settings(), state)
    assert not source_sync.sync_if_due(make_settings(), state)
    assert len(requests) == 1


def test_environment_file_controls_schedule_on_each_invocation(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SOURCE_SYNC_ENABLED=false\nSOURCE_SYNC_INTERVAL_SECONDS=600\n")
    settings = Settings(_env_file=env_file)
    assert not settings.source_sync_enabled
    assert settings.source_sync_interval_seconds == 600
    env_file.write_text("SOURCE_SYNC_ENABLED=true\nSOURCE_SYNC_INTERVAL_SECONDS=120\n")
    settings = Settings(_env_file=env_file)
    assert settings.source_sync_enabled
    assert settings.source_sync_interval_seconds == 120


@pytest.mark.parametrize("value", [0, -1])
def test_interval_must_be_positive(value):
    with pytest.raises(ValueError):
        make_settings(source_sync_interval_seconds=value)


def test_clock_rollback_does_not_block_sync(tmp_path, monkeypatch):
    mock_client(monkeypatch, httpx.Response(200, json={"errors": []}))
    state = tmp_path / "last-attempt"
    state.write_text("20000")
    monkeypatch.setattr(source_sync.time, "time", lambda: 10000)
    assert source_sync.sync_if_due(make_settings(), state)


def test_main_reports_failure(tmp_path, monkeypatch, caplog):
    mock_client(monkeypatch, httpx.Response(200, json={"errors": ["unavailable"]}))
    monkeypatch.setattr("sys.argv", ["source_sync", "--state-file", str(tmp_path / "last-attempt")])
    assert source_sync.main() == 1
    assert "partial failures" in caplog.text