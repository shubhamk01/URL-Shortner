"""Audit-grade append-only event log (JSON Lines) — one line per recorded event."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..policies.guardrails import redact


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AuditEvent:
    run_id: str
    action: str
    actor: str
    status: str
    timestamp: datetime = field(default_factory=utcnow)
    task_id: Optional[str] = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["details"] = json.loads(redact(json.dumps(self.details)))
        return d


class AuditLog:
    """Writes to <runs_dir>/<run_id>/events.jsonl. Never store secrets or raw prompt text."""

    def __init__(self, runs_dir: str):
        self.runs_dir = Path(runs_dir)

    def _events_path(self, run_id: str) -> Path:
        d = self.runs_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d / "events.jsonl"

    def record(
        self,
        run_id: str,
        action: str,
        actor: str,
        status: str,
        task_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> AuditEvent:
        event = AuditEvent(run_id=run_id, action=action, actor=actor, status=status,
                           task_id=task_id, details=details or {})
        with self._events_path(run_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict()) + "\n")
        return event

    def read_events(self, run_id: str) -> list[dict]:
        path = self._events_path(run_id)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read_all_events(self) -> list[dict]:
        events: list[dict] = []
        if not self.runs_dir.exists():
            return events
        for run_dir in self.runs_dir.iterdir():
            if run_dir.is_dir():
                events.extend(self.read_events(run_dir.name))
        return events
