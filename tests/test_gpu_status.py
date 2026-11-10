import json
from time import time

import pytest

from rosie import gpu_status


def write_status(path, **overrides) -> None:
    data = {"updated_at": time(), "state": "ok", "fan_mode": "full", "gpu": {"temperature_c": 73}}
    data.update(overrides)
    path.write_text(json.dumps(data))


CPUINFO = """processor\t: 0
model name\t: Intel(R) Xeon(R) CPU E3-1241 v3 @ 3.50GHz
physical id\t: 0
core id\t\t: 0

processor\t: 1
model name\t: Intel(R) Xeon(R) CPU E3-1241 v3 @ 3.50GHz
physical id\t: 0
core id\t\t: 1

processor\t: 2
model name\t: Intel(R) Xeon(R) CPU E3-1241 v3 @ 3.50GHz
physical id\t: 0
core id\t\t: 0
"""


@pytest.fixture
def status_file(tmp_path, monkeypatch):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(CPUINFO)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       32817784 kB\nMemFree:         1000000 kB\n")
    monkeypatch.setattr(gpu_status, "CPUINFO_PATH", cpuinfo)
    monkeypatch.setattr(gpu_status, "MEMINFO_PATH", meminfo)
    gpu_status.host_info.cache_clear()
    monkeypatch.setattr(gpu_status, "_gpu_info", None)
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


HOST = {
    "cpu_model": "Intel Xeon E3-1241 v3 @ 3.50GHz",
    "cpu_cores": 2,
    "cpu_threads": 3,
    "memory_total_mib": 32048,
}


def test_system_reports_host_cpu_and_memory_without_p4_thermal(status_file) -> None:
    assert gpu_status.system_status() == {**HOST, "gpu": None}
    assert "system" not in gpu_status.gpu_status()


def test_system_keeps_fixed_gpu_details_even_when_status_goes_stale(status_file) -> None:
    gpu = {"name": "Tesla P4", "temperature_c": 54, "memory_used_mib": 6207, "memory_total_mib": 7680, "max_sm_clock_mhz": 1531}
    write_status(status_file, updated_at=time() - 3600, gpu=gpu)
    expected = {**HOST, "gpu": {"name": "Tesla P4", "memory_total_mib": 7680, "max_sm_clock_mhz": 1531}}
    assert gpu_status.system_status() == expected
    status_file.unlink()
    assert gpu_status.system_status() == expected


def test_unreadable_proc_files_leave_system_fields_empty(status_file, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gpu_status, "CPUINFO_PATH", tmp_path / "missing")
    monkeypatch.setattr(gpu_status, "MEMINFO_PATH", tmp_path / "missing")
    gpu_status.host_info.cache_clear()
    assert gpu_status.system_status() == {
        "cpu_model": None, "cpu_cores": None, "cpu_threads": None, "memory_total_mib": None, "gpu": None,
    }
