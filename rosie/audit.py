import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rosie.config import settings


def record(event: str, details: dict[str, Any]) -> None:
    path = Path(settings.audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(UTC).isoformat(), "event": event, **details}
    with path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(entry, ensure_ascii=True) + "\n")
