import argparse
import importlib.util
import json
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "host" / "p4-thermal.py"


@pytest.fixture(scope="module")
def p4():
    spec = importlib.util.spec_from_file_location("p4_thermal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_args(tmp_path=None, **overrides) -> argparse.Namespace:
    values = {
        "full_above": 84,
        "optimal_below": 55,
        "cool_hold": 120.0,
        "warn_temp": 80,
        "critical_temp": 85,
        "max_failures": 3,
        "reassert": 60.0,
        "status_path": str(tmp_path / "status.json") if tmp_path else "/nonexistent/status.json",
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_hot_gpu_selects_full(p4) -> None:
    controller = p4.Controller(make_args())
    assert controller.decide(84, 1000.0) == "full"


def test_normal_startup_stays_optimal_below_full_threshold(p4) -> None:
    controller = p4.Controller(make_args())
    assert controller.decide(83, 1000.0) == "optimal"


def test_optimal_only_after_cool_hold(p4) -> None:
    controller = p4.Controller(make_args())
    controller.mode = "full"
    assert controller.decide(50, 1000.0) == "full"
    assert controller.decide(50, 1060.0) == "full"
    assert controller.decide(50, 1121.0) == "optimal"


def test_between_thresholds_keeps_current_mode(p4) -> None:
    controller = p4.Controller(make_args())
    controller.mode = "optimal"
    assert controller.decide(60, 1000.0) == "optimal"
    controller.mode = "full"
    assert controller.decide(60, 1000.0) == "full"


def test_heat_restarts_the_cool_timer(p4) -> None:
    controller = p4.Controller(make_args())
    controller.mode = "full"
    controller.decide(50, 1000.0)
    controller.decide(66, 1100.0)  # hot again before the hold elapsed
    assert controller.decide(50, 1130.0) == "full"
    assert controller.decide(50, 1251.0) == "optimal"


def test_unknown_temperature_selects_full(p4) -> None:
    controller = p4.Controller(make_args())
    controller.mode = "optimal"
    assert controller.decide(None, 1000.0) == "full"


@pytest.mark.parametrize(
    ("temp", "throttled", "expected"),
    [(60, False, "ok"), (80, False, "warning"), (85, False, "critical"), (60, True, "critical")],
)
def test_status_state(p4, temp: int, throttled: bool, expected: str) -> None:
    controller = p4.Controller(make_args())
    gpu = {"temperature_c": temp, "thermally_throttled": throttled}
    assert controller.build_status(time.time(), gpu, [], [])["state"] == expected


def test_status_is_error_without_gpu(p4) -> None:
    controller = p4.Controller(make_args())
    assert controller.build_status(time.time(), None, [], ["gpu: boom"])["state"] == "error"


def test_read_gpu_parses_csv_and_throttle_flags(p4, monkeypatch) -> None:
    line = "88, 455, 1531, 38.92, 100, 6205, 7680, P0, 0x0000000000000068, Tesla P4\n"

    def fake_run(cmd, timeout=10.0):
        assert cmd == [
            "nvidia-smi",
            f"--query-gpu={p4.GPU_QUERY}",
            "--format=csv,noheader,nounits",
        ]
        assert p4.GPU_QUERY.split(",")[-1] == "name"
        return line

    monkeypatch.setattr(p4, "run", fake_run)
    gpu = p4.read_gpu()
    assert gpu["name"] == "Tesla P4"
    assert gpu["temperature_c"] == 88
    assert gpu["sm_clock_mhz"] == 455
    assert gpu["power_w"] == 38.92
    assert gpu["memory_used_mib"] == 6205
    assert gpu["memory_total_mib"] == 7680
    assert gpu["thermally_throttled"] is True
    assert {"sw_thermal_slowdown", "hw_thermal_slowdown", "hw_slowdown"} <= set(gpu["throttle_reasons"])


def test_read_gpu_handles_unavailable_fields(p4, monkeypatch) -> None:
    line = "70, 746, 1531, [N/A], 0, [N/A], [N/A], P0, 0x0000000000000000, [N/A]\n"
    monkeypatch.setattr(p4, "run", lambda cmd, timeout=10.0: line)
    gpu = p4.read_gpu()
    assert gpu["power_w"] is None
    assert gpu["name"] is None
    assert gpu["memory_used_mib"] is None
    assert gpu["memory_total_mib"] is None
    assert gpu["thermally_throttled"] is False
    assert gpu["throttle_reasons"] == []


def test_read_gpu_handles_quoted_model_and_uses_first_gpu(p4, monkeypatch) -> None:
    line = (
        '70, 746, 1531, 20, 0, 0, 7680, P0, 0x0, "Example GPU, Model 1"\n'
        "60, 746, 1531, 20, 0, 100, 8192, P0, 0x0, Second GPU\n"
    )
    monkeypatch.setattr(p4, "run", lambda cmd, timeout=10.0: line)
    gpu = p4.read_gpu()
    assert gpu["name"] == "Example GPU, Model 1"
    assert gpu["memory_used_mib"] == 0
    assert gpu["memory_total_mib"] == 7680


@pytest.mark.parametrize("line", ["", "70, 746, 1531, 20, 0, 100, 7680, P0, 0x0\n"])
def test_read_gpu_rejects_missing_fields(p4, monkeypatch, line) -> None:
    monkeypatch.setattr(p4, "run", lambda cmd, timeout=10.0: line)
    with pytest.raises(RuntimeError):
        p4.read_gpu()


def test_read_fans_ignores_missing_sensors(p4, monkeypatch) -> None:
    output = (
        "FAN1             | 41h | ok  | 29.1 | 3500 RPM\n"
        "FAN2             | 42h | ns  | 29.2 | No Reading\n"
        "FANA             | 45h | ns  | 29.5 | No Reading\n"
    )
    monkeypatch.setattr(p4, "run", lambda cmd, timeout=10.0: output)
    assert p4.read_fans() == [{"name": "FAN1", "rpm": 3500}]


def test_single_gpu_failure_is_tolerated_then_fails_safe(p4, monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    def fail():
        raise RuntimeError("NVML error")

    monkeypatch.setattr(p4, "read_gpu", fail)
    monkeypatch.setattr(p4, "read_fans", lambda: [])
    monkeypatch.setattr(p4, "set_fan_mode", calls.append)
    controller = p4.Controller(make_args(tmp_path))

    first = controller.step()
    second = controller.step()
    assert first["fan_mode"] == second["fan_mode"] == "optimal"
    assert calls == ["optimal"]

    status = controller.step()  # third consecutive failure
    assert controller.mode == "full"
    assert calls == ["optimal", "full"]
    assert status["state"] == "error"


def test_step_writes_status_file(p4, monkeypatch, tmp_path) -> None:
    gpu = {"temperature_c": 72, "thermally_throttled": False}
    monkeypatch.setattr(p4, "read_gpu", lambda: gpu)
    monkeypatch.setattr(p4, "read_fans", lambda: [{"name": "FAN1", "rpm": 3500}])
    monkeypatch.setattr(p4, "set_fan_mode", lambda name: None)
    controller = p4.Controller(make_args(tmp_path))

    controller.step()

    written = json.loads((tmp_path / "status.json").read_text())
    assert written["state"] == "ok"
    assert written["fan_mode"] == "optimal"
    assert written["fans"] == [{"name": "FAN1", "rpm": 3500}]


def test_dry_run_never_sets_the_fan_mode(p4, monkeypatch, tmp_path) -> None:
    def forbidden(name: str) -> None:
        raise AssertionError("set_fan_mode must not run in dry-run mode")

    monkeypatch.setattr(p4, "read_gpu", lambda: {"temperature_c": 70, "thermally_throttled": False})
    monkeypatch.setattr(p4, "read_fans", lambda: [])
    monkeypatch.setattr(p4, "set_fan_mode", forbidden)
    controller = p4.Controller(make_args(tmp_path, dry_run=True))
    assert controller.step()["fan_mode"] == "optimal"
