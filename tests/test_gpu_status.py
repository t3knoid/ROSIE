import json
from time import time

import pytest

from rosie import gpu_status


def write_status(path, **overrides) -> None:
    data = {"updated_at": time(), "state": "ok", "fan_mode": "full", "gpu": {"temperature_c": 73}}
    data.update(overrides)
    path.write_text(json.dumps(data))


@pytest.fixture
def status_file(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    monkeypatch.setattr(gpu_status, "STATUS_PATH", path)
    monkeypatch.setattr(gpu_status, "MAX_AGE_SECONDS", 30.0)
    return path


def test_reports_unavailable_when_file_is_missing(status_file) -> None:
    result = gpu_status.gpu_status()
    assert result["available"] is False
    assert "not found" in str(result["reason"]).lower()


def test_returns_fresh_status_with_age(status_file) -> None:
    write_status(status_file)
    result = gpu_status.gpu_status()
    assert result["available"] is True
    assert result["stale"] is False
    assert result["age_seconds"] < 5
    assert result["gpu"] == {"temperature_c": 73}
    assert result["fan_mode"] == "full"


def test_marks_old_status_as_stale(status_file) -> None:
    write_status(status_file, updated_at=time() - 120)
    result = gpu_status.gpu_status()
    assert result["available"] is True
    assert result["stale"] is True
    assert result["age_seconds"] >= 120


def test_preserves_gpu_model_and_live_memory_values(status_file) -> None:
    for used_memory in (0, 6205):
        gpu = {
            "name": "Tesla P4",
            "temperature_c": 73,
            "memory_used_mib": used_memory,
            "memory_total_mib": 7680,
        }
        write_status(status_file, gpu=gpu)
        result = gpu_status.gpu_status()
        assert result["stale"] is False
        assert result["gpu"] == gpu


def test_status_without_timestamp_is_stale(status_file) -> None:
    status_file.write_text(json.dumps({"state": "ok"}))
    result = gpu_status.gpu_status()
    assert result["available"] is True
    assert result["stale"] is True


@pytest.mark.parametrize("content", ["{bad", "", "[]", "null", '"text"'])
def test_unreadable_or_malformed_status_is_unavailable(status_file, content: str) -> None:
    status_file.write_text(content)
    result = gpu_status.gpu_status()
    assert result["available"] is False
    assert result["reason"]
