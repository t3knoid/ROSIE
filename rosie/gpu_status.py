"""Read-only GPU/fan status for ROSIE.

The host service p4-thermal writes a JSON file; this router only reads it. ROSIE never
touches the BMC or nvidia-smi, so it stays consistent with its documentation-only design.
"""
import json
import os
from pathlib import Path
from time import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/health", tags=["Health"])

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


@router.get(
    "/gpu",
    summary="Get GPU and fan status",
    responses={200: {"model": GpuStatus, "description": "The latest status, or `available: false` with a `reason`."}},
)
def gpu_status() -> dict[str, object]:
    """Return the latest GPU model, VRAM use, temperature, clocks, throttle flags, and fan speeds.

    Reads the JSON file written by the optional host `p4-thermal` service (default
    `/run/p4-thermal/status.json`). ROSIE only reads this file; it never controls the
    fans or queries the GPU itself. Always returns 200; check `available` and `stale`.
    """
    try:
        data = json.loads(STATUS_PATH.read_text())
    except FileNotFoundError:
        return {"available": False, "reason": "Status file not found. Is p4-thermal running and mounted?"}
    except (OSError, ValueError) as error:
        return {"available": False, "reason": f"Could not read GPU status: {error}"}
    if not isinstance(data, dict):
        return {"available": False, "reason": "GPU status file has an unexpected format"}

    age = max(0.0, time() - float(data.get("updated_at") or 0))
    data["available"] = True
    data["age_seconds"] = round(age, 1)
    data["stale"] = age > MAX_AGE_SECONDS
    return data
