from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass
class AuditEvent:
    timestamp_utc: str
    module: str
    action: str
    actor_role: str
    target: str
    status: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """Lightweight reusable audit logger with optional JSONL persistence."""

    def __init__(self, module: str, log_path: Path | None = None):
        self.module = module
        self.events: list[AuditEvent] = []
        if log_path is None:
            from core.config import DATA_DIR
            log_dir = DATA_DIR / "audit_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{module}.jsonl"
        self.log_path = log_path

    def record(
        self,
        action: str,
        actor_role: str = "System",
        target: str = "",
        status: str = "SUCCESS",
        details: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> AuditEvent:
        event = AuditEvent(
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            module=self.module,
            action=action,
            actor_role=actor_role,
            target=target,
            status=status,
            details=details or {},
        )
        self.events.append(event)
        if persist and self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict(), ensure_ascii=False, default=str) + "\n")
        return event

    def to_dicts(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]
