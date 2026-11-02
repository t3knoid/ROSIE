"""Read-only GPU/fan status for ROSIE.

The host service p4-thermal writes a JSON file; this router only reads it. ROSIE never
touches the BMC or nvidia-smi, so it stays consistent with its documentation-only design.
Place this file at rosie/gpu_status.py.
"""
import json
import os
from pathlib import Path
from time import time

from fastapi import APIRouter

router = APIRouter(prefix="/api/health", tags=["health"])

STATUS_PATH = Path(os.environ.get("ROSIE_GPU_STATUS_PATH", "/run/p4-thermal/status.json"))
MAX_AGE_SECONDS = float(os.environ.get("ROSIE_GPU_STATUS_MAX_AGE", "30"))


@router.get("/gpu")
def gpu_status() -> dict[str, object]:
    """Latest GPU model, VRAM use, temperature, clocks, throttle flags and fan RPM."""
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
