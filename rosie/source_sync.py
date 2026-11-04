import argparse
import logging
from pathlib import Path
import time

import httpx

from rosie.config import Settings


logger = logging.getLogger(__name__)


def sync_if_due(settings: Settings, state_path: Path) -> bool:
    if not settings.source_sync_enabled:
        return False
    now = time.time()
    try:
        last_attempt = float(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        last_attempt = None
    if last_attempt is not None and 0 <= now - last_attempt < settings.source_sync_interval_seconds:
        return False

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(str(now), encoding="utf-8")
    with httpx.Client(timeout=settings.source_sync_timeout_seconds, follow_redirects=False) as client:
        response = client.post(settings.source_sync_api_url)
        response.raise_for_status()
        result = response.json()
    if not isinstance(result, dict) or not isinstance(result.get("errors"), list):
        raise ValueError("Source sync returned an invalid response")
    if result["errors"]:
        raise ValueError(f"Source sync reported partial failures: {result['errors']}")
    logger.info("Source sync completed: %s", result)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync configured ROSIE sources when due")
    parser.add_argument("--state-file", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        sync_if_due(Settings(), args.state_file)
    except (httpx.HTTPError, OSError, ValueError) as error:
        logger.error("Source sync failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())