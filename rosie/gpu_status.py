"""Read-only hardware information for ROSIE.

`GET /api/health/system` reports what does not change while ROSIE runs: the CPU, total memory,
and the GPU model, VRAM size and maximum clock. `GET /api/health/gpu` reports live readings.

The host service p4-thermal writes a JSON file; this router only reads it. ROSIE never
touches the BMC or nvidia-smi, so it stays consistent with its documentation-only design.
"""
from functools import lru_cache
import json
import os
import re
from pathlib import Path
from time import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/health", tags=["Health"])

CPUINFO_PATH = Path("/proc/cpuinfo")
MEMINFO_PATH = Path("/proc/meminfo")
STATUS_PATH = Path(os.environ.get("ROSIE_GPU_STATUS_PATH", "/run/p4-thermal/status.json"))
MAX_AGE_SECONDS = float(os.environ.get("ROSIE_GPU_STATUS_MAX_AGE", "30"))


# These models document the response only. The handler passes the status file through
# unchanged, so they are not used for validation and allow extra fields.
class GpuReading(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = Field(None, description="GPU model name.", examples=["Tesla P4"])
    temperature_c: int | None = Field(None, description="Core temperature in °C.", examples=[71])
    sm_clock_mhz: int | None = Field(None, description="Current SM clock.", examples=[1531])
    max_sm_clock_mhz: int | None = Field(None, description="Maximum SM clock.", examples=[1531])
    power_w: float | None = Field(None, description="Power draw in watts.", examples=[48.3])
    utilization_pct: int | None = Field(None, description="GPU utilization.", examples=[97])
    memory_used_mib: int | None = Field(None, description="VRAM in use.", examples=[6205])
    memory_total_mib: int | None = Field(None, description="Total VRAM.", examples=[7680])
    pstate: str | None = Field(None, description="Performance state.", examples=["P0"])
    throttle_reasons: list[str] = Field(default_factory=list, description="Active clock-limiting reasons reported by nvidia-smi.")
    thermally_throttled: bool | None = Field(None, description="`true` when a thermal slowdown is active.")


class GpuInfo(BaseModel):
    name: str | None = Field(None, description="GPU model name.", examples=["Tesla P4"])
    memory_total_mib: int | None = Field(None, description="Total VRAM.", examples=[7680])
    max_sm_clock_mhz: int | None = Field(None, description="Maximum SM clock.", examples=[1531])


class SystemInfo(BaseModel):
    cpu_model: str | None = Field(None, description="CPU model name.", examples=["Intel Xeon E3-1241 v3 @ 3.50GHz"])
    cpu_cores: int | None = Field(None, description="Physical CPU cores.", examples=[4])
    cpu_threads: int | None = Field(None, description="Logical CPUs (threads).", examples=[8])
    memory_total_mib: int | None = Field(None, description="Total system memory usable by the OS.", examples=[32048])
    gpu: GpuInfo | None = Field(None, description="The GPU's fixed details, or `null` until p4-thermal has reported them once.")


class FanReading(BaseModel):
    name: str = Field(examples=["FAN1"])
    rpm: int = Field(examples=[8400])


class GpuStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool = Field(description="`false` when the status file is missing or unreadable; only `reason` is then present.")
    reason: str | None = Field(None, description="Why the status is unavailable.")
    stale: bool | None = Field(None, description="`true` when the file is older than `ROSIE_GPU_STATUS_MAX_AGE` seconds (default 30).")
    age_seconds: float | None = Field(None, description="Seconds since the controller last wrote the file.")
    updated_at: float | None = Field(None, description="Unix time the controller wrote the file.")
    state: Literal["ok", "warning", "critical", "error", "stopped"] | None = Field(
        None,
        description="`ok`; `warning` (hot); `critical` (throttling or at the critical temperature); `error` (GPU unreadable); `stopped` (controller shut down).",
    )
    fan_mode: str | None = Field(None, description="BMC fan mode last applied, such as `optimal` or `full`.")
    gpu: GpuReading | None = None
    fans: list[FanReading] = Field(default_factory=list)
    thresholds: dict[str, int] | None = Field(None, description="Controller temperature thresholds in °C.")
    errors: list[str] = Field(default_factory=list, description="Problems in the controller's latest cycle.")


GPU_INFO_FIELDS = ("name", "memory_total_mib", "max_sm_clock_mhz")
_gpu_info: dict[str, object] | None = None
"""The GPU's fixed details, kept from the first status file that has them."""


@lru_cache(maxsize=1)
def host_info() -> dict[str, object]:
    """The host's CPU model, core and thread counts, and total memory.

    A container sees the host's /proc/cpuinfo and /proc/meminfo, so these are the server's
    values. They do not change while ROSIE runs, so they are read once.
    """
    info: dict[str, object] = {"cpu_model": None, "cpu_cores": None, "cpu_threads": None, "memory_total_mib": None}
    try:
        blocks = [block for block in CPUINFO_PATH.read_text().split("\n\n") if block.strip()]
        processors = [dict(_fields(block)) for block in blocks]
        processors = [cpu for cpu in processors if "processor" in cpu]
        if processors:
            info["cpu_threads"] = len(processors)
            model = processors[0].get("model name")
            if model:
                info["cpu_model"] = re.sub(r"\s+", " ", re.sub(r"\((R|TM)\)|\bCPU\b", "", model)).strip()
            cores = {(cpu.get("physical id"), cpu.get("core id")) for cpu in processors if "core id" in cpu}
            info["cpu_cores"] = len(cores) or None
    except OSError:
        pass
    try:
        meminfo = dict(_fields(MEMINFO_PATH.read_text()))
        kib = int(meminfo["MemTotal"].split()[0])
        info["memory_total_mib"] = kib // 1024
    except (OSError, KeyError, ValueError, IndexError):
        pass
    return info


def _read_status() -> dict[str, object]:
    """The p4-thermal status file's contents. Raises OSError or ValueError if unreadable."""
    data = json.loads(STATUS_PATH.read_text())
    if not isinstance(data, dict):
        raise ValueError("GPU status file has an unexpected format")
    return data


def gpu_info() -> dict[str, object] | None:
    """The GPU's model, VRAM size and maximum clock, from p4-thermal's status file.

    These do not change, so the file's age does not matter, and once read they are kept.
    """
    global _gpu_info
    if _gpu_info is None:
        try:
            gpu = _read_status().get("gpu")
        except (OSError, ValueError):
            gpu = None
        if isinstance(gpu, dict) and gpu.get("name"):
            _gpu_info = {field: gpu.get(field) for field in GPU_INFO_FIELDS}
    return _gpu_info


def _fields(text: str):
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            yield key.strip(), value.strip()


@router.get(
    "/gpu",
    summary="Get GPU and fan status",
    responses={200: {"model": GpuStatus, "description": "The latest status, or `available: false` with a `reason`."}},
)
def gpu_status() -> dict[str, object]:
    """Return the host's CPU and memory, and the latest GPU model, VRAM use, temperature, clocks, throttle flags, and fan speeds.

    Reads the JSON file written by the optional host `p4-thermal` service (default
    `/run/p4-thermal/status.json`). ROSIE only reads this file; it never controls the
    fans or queries the GPU itself. Always returns 200; check `available` and `stale`.
    For the hardware's fixed details, use `GET /api/health/system`.
    """
    try:
        data = _read_status()
    except FileNotFoundError:
        return {"available": False, "reason": "Status file not found. Is p4-thermal running and mounted?"}
    except (OSError, ValueError) as error:
        return {"available": False, "reason": f"Could not read GPU status: {error}"}

    age = max(0.0, time() - float(data.get("updated_at") or 0))
    data["available"] = True
    data["age_seconds"] = round(age, 1)
    data["stale"] = age > MAX_AGE_SECONDS
    return data


@router.get(
    "/system",
    summary="Get the server's CPU, memory and GPU",
    responses={200: {"model": SystemInfo, "description": "Fields that cannot be read are `null`."}},
)
def system_status() -> dict[str, object]:
    """Return the server's fixed hardware details: CPU model, core and thread counts, total
    memory, and the GPU model, VRAM size and maximum clock.

    CPU and memory are read from `/proc`. The GPU details come from the optional p4-thermal
    status file and are `null` until it has reported them once. Always returns 200.
    """
    return {**host_info(), "gpu": gpu_info()}
