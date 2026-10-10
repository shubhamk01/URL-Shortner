"""Persistent run/plan state on local disk (JSON files) — survives process restarts
and lets a reviewer inspect the plan/dependency graph directly as files.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..planning.models import PlanVersion


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunRecord:
    run_id: str
    requirement_text: str
    mode: str
    status: str = "RUNNING"  # RUNNING | COMPLETED | FAILED | STOPPED
    created_at: datetime = field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_plan_id: Optional[str] = None
    current_plan_version: int = 1
    safe_stop_requested: bool = False

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        for key in ("created_at", "started_at", "completed_at"):
            v = d[key]
            d[key] = v.isoformat() if v else None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RunRecord":
        data = dict(data)
        for key in ("created_at", "started_at", "completed_at"):
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)


class StateStore:
    def __init__(self, runs_dir: str):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        d = self.runs_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def artifacts_dir(self, run_id: str) -> Path:
        d = self.run_dir(run_id) / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def plans_dir(self, run_id: str) -> Path:
        d = self.run_dir(run_id) / "plans"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_run(self, run: RunRecord) -> None:
        path = self.run_dir(run.run_id) / "run.json"
        path.write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")

    def load_run(self, run_id: str) -> RunRecord:
        path = self.run_dir(run_id) / "run.json"
        return RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_plan(self, plan: PlanVersion) -> None:
        path = self.plans_dir(plan.run_id) / f"plan-v{plan.version}.json"
        path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
        latest = self.run_dir(plan.run_id) / "current_plan.json"
        latest.write_text(json.dumps({"plan_id": plan.plan_id, "version": plan.version}), encoding="utf-8")

    def load_plan(self, run_id: str, version: Optional[int] = None) -> PlanVersion:
        if version is None:
            pointer = json.loads((self.run_dir(run_id) / "current_plan.json").read_text(encoding="utf-8"))
            version = pointer["version"]
        path = self.plans_dir(run_id) / f"plan-v{version}.json"
        return PlanVersion.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_runs(self) -> list[str]:
        return sorted(p.name for p in self.runs_dir.iterdir() if p.is_dir())
