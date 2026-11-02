#!/usr/bin/env python3
"""Thermal controller for a passively cooled Tesla P4 in a Supermicro X10 chassis.

Every few seconds it reads the GPU with nvidia-smi, picks a BMC fan mode (Full or
Optimal) with hysteresis, and writes a JSON status file that ROSIE serves read-only.
The BMC cannot see the GPU's temperature, so this is what lets the fans follow it.

Fail-safe behaviour:
  * If the GPU cannot be read several times in a row, the fans go to Full.
  * When the service stops, the fans go to Full (the systemd unit also does this
    in ExecStopPost, which covers crashes and kill -9).

Needs root (ipmitool talks to /dev/ipmi0).
Try it first with:  sudo ./p4-thermal.py --once --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

log = logging.getLogger("p4-thermal")

NVIDIA_SMI = "nvidia-smi"
IPMITOOL = "ipmitool"

# Supermicro X9/X10 BMC fan presets: ipmitool raw 0x30 0x45 0x01 <mode>
FAN_MODES = {"standard": 0x00, "full": 0x01, "optimal": 0x02, "heavyio": 0x04}

GPU_QUERY = (
    "temperature.gpu,clocks.sm,clocks.max.sm,power.draw,utilization.gpu,"
    "memory.used,memory.total,pstate,clocks_event_reasons.active"
)

THROTTLE_BITS = {
    0x01: "gpu_idle",
    0x02: "applications_clocks_setting",
    0x04: "sw_power_cap",
    0x08: "hw_slowdown",
    0x10: "sync_boost",
    0x20: "sw_thermal_slowdown",
    0x40: "hw_thermal_slowdown",
    0x80: "hw_power_brake_slowdown",
}
THERMAL_THROTTLE_MASK = 0x20 | 0x40


def run(cmd: list[str], timeout: float = 10.0) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{cmd[0]} exited {result.returncode}: {detail}")
    return result.stdout


def _int(text: str) -> int | None:
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def read_gpu() -> dict:
    out = run([NVIDIA_SMI, f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"])
    lines = out.strip().splitlines()
    if not lines:
        raise RuntimeError("nvidia-smi returned no GPUs")
    fields = [f.strip() for f in lines[0].split(",")]
    if len(fields) < 9:
        raise RuntimeError(f"unexpected nvidia-smi output: {lines[0]!r}")
    try:
        mask = int(fields[8], 16)
    except ValueError:
        mask = 0
    return {
        "temperature_c": _int(fields[0]),
        "sm_clock_mhz": _int(fields[1]),
        "max_sm_clock_mhz": _int(fields[2]),
        "power_w": _float(fields[3]),
        "utilization_pct": _int(fields[4]),
        "memory_used_mib": _int(fields[5]),
        "memory_total_mib": _int(fields[6]),
        "pstate": fields[7],
        "throttle_reasons": [name for bit, name in THROTTLE_BITS.items() if mask & bit],
        "thermally_throttled": bool(mask & THERMAL_THROTTLE_MASK),
    }


def read_fans() -> list[dict]:
    fans = []
    for line in run([IPMITOOL, "sdr", "type", "Fan"]).splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        match = re.match(r"(\d+(?:\.\d+)?)\s*RPM", parts[4], re.IGNORECASE)
        if match:
            fans.append({"name": parts[0], "rpm": int(float(match.group(1)))})
    return fans


def set_fan_mode(name: str) -> None:
    run([IPMITOOL, "raw", "0x30", "0x45", "0x01", f"0x{FAN_MODES[name]:02x}"])


def write_status(path: Path, status: dict) -> None:
    """Write atomically so ROSIE never reads a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(status, handle)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Controller:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.mode: str | None = None  # last fan mode successfully applied
        self.cool_since: float | None = None
        self.last_apply = 0.0
        self.failures = 0

    def decide(self, temp: int | None, now: float) -> str:
        """Full when hot, Optimal only after staying cool for a while, else hold."""
        if temp is None or temp >= self.args.full_above:
            self.cool_since = None
            return "full"
        if temp <= self.args.optimal_below:
            if self.cool_since is None:
                self.cool_since = now
            if now - self.cool_since >= self.args.cool_hold:
                return "optimal"
        else:
            self.cool_since = None
        return self.mode or "optimal"

    def apply(self, desired: str, now: float) -> str | None:
        """Set the fan mode if it changed (or is due for re-assertion). Returns an error string."""
        if desired == self.mode and now - self.last_apply < self.args.reassert:
            return None
        if self.args.dry_run:
            log.info("dry-run: would set fan mode %s", desired)
        else:
            try:
                set_fan_mode(desired)
            except Exception as error:  # noqa: BLE001 - report and keep running
                log.error("could not set fan mode %s: %s", desired, error)
                return str(error)
        if desired != self.mode:
            log.info("fan mode -> %s", desired)
        self.mode = desired
        self.last_apply = now
        return None

    def build_status(self, now: float, gpu: dict | None, fans: list[dict], errors: list[str]) -> dict:
        temp = gpu["temperature_c"] if gpu else None
        if gpu is None:
            state = "error"
        elif gpu["thermally_throttled"] or (temp is not None and temp >= self.args.critical_temp):
            state = "critical"
        elif temp is not None and temp >= self.args.warn_temp:
            state = "warning"
        else:
            state = "ok"
        return {
            "updated_at": now,
            "state": state,
            "fan_mode": self.mode,
            "gpu": gpu,
            "fans": fans,
            "thresholds": {
                "full_above_c": self.args.full_above,
                "optimal_below_c": self.args.optimal_below,
                "warn_c": self.args.warn_temp,
                "critical_c": self.args.critical_temp,
            },
            "errors": errors,
        }

    def step(self) -> dict:
        now = time.time()
        errors: list[str] = []
        gpu = None
        try:
            gpu = read_gpu()
            self.failures = 0
        except Exception as error:  # noqa: BLE001
            self.failures += 1
            errors.append(f"gpu: {error}")
            log.warning("GPU read failed (%d/%d): %s", self.failures, self.args.max_failures, error)

        if gpu is not None:
            desired = self.decide(gpu["temperature_c"], now)
        elif self.failures >= self.args.max_failures:
            desired = "full"  # cannot see the GPU: fail safe
        else:
            desired = self.mode or "optimal"  # ride out transient startup read failures

        fan_error = self.apply(desired, now)
        if fan_error:
            errors.append(f"fan mode: {fan_error}")

        fans: list[dict] = []
        try:
            fans = read_fans()
        except Exception as error:  # noqa: BLE001
            errors.append(f"fans: {error}")

        status = self.build_status(now, gpu, fans, errors)
        try:
            write_status(Path(self.args.status_path), status)
        except OSError as error:
            log.error("could not write %s: %s", self.args.status_path, error)
        return status

    def shutdown(self) -> None:
        log.info("stopping; leaving fans on Full")
        if not self.args.dry_run:
            try:
                set_fan_mode("full")
            except Exception as error:  # noqa: BLE001
                log.error("could not set Full on shutdown: %s", error)
        try:
            write_status(
                Path(self.args.status_path),
                {"updated_at": time.time(), "state": "stopped", "fan_mode": "full", "gpu": None, "fans": [], "errors": []},
            )
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interval", type=float, default=5.0, help="seconds between polls (default 5)")
    p.add_argument("--full-above", type=int, default=84, help="go to Full at or above this temp in C (default 84)")
    p.add_argument("--optimal-below", type=int, default=55, help="allow Optimal at or below this temp in C (default 55)")
    p.add_argument("--cool-hold", type=float, default=120.0, help="seconds the GPU must stay cool before Optimal (default 120)")
    p.add_argument("--warn-temp", type=int, default=80, help="status 'warning' at or above this temp (default 80)")
    p.add_argument("--critical-temp", type=int, default=85, help="status 'critical' at or above this temp (default 85)")
    p.add_argument("--max-failures", type=int, default=3, help="consecutive GPU read failures before forcing Full (default 3)")
    p.add_argument("--reassert", type=float, default=60.0, help="re-send the fan mode this often in seconds (default 60)")
    p.add_argument("--status-path", default="/run/p4-thermal/status.json")
    p.add_argument("--once", action="store_true", help="do one cycle, print the status and exit")
    p.add_argument("--dry-run", action="store_true", help="never change the fan mode")
    args = p.parse_args()
    if args.optimal_below >= args.full_above:
        p.error("--optimal-below must be lower than --full-above")
    return args


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    controller = Controller(args)

    if args.once:
        print(json.dumps(controller.step(), indent=2))
        return 0

    stop = {"now": False}

    def handle(signum, frame):  # noqa: ARG001
        stop["now"] = True

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)

    log.info(
        "started: Full at >=%dC, Optimal after %ds at <=%dC, interval %.0fs%s",
        args.full_above, args.cool_hold, args.optimal_below, args.interval,
        " (dry run)" if args.dry_run else "",
    )
    while not stop["now"]:
        controller.step()
        deadline = time.monotonic() + args.interval
        while not stop["now"] and time.monotonic() < deadline:
            time.sleep(0.5)
    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
