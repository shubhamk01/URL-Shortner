"""Human approval gate: pause/resume with approver, timestamp, rationale, and outcome recorded."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..planning.models import Task


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ApprovalRecord:
    task_id: str
    run_id: str
    requested_at: datetime
    decided_at: datetime
    approver: str
    decision: str  # "APPROVED" | "REJECTED"
    rationale: str
    resolution_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "requested_at": self.requested_at.isoformat(),
            "decided_at": self.decided_at.isoformat(),
            "approver": self.approver,
            "decision": self.decision,
            "rationale": self.rationale,
            "resolution_notes": self.resolution_notes,
        }


DecisionFn = Callable[["Task"], dict]


def auto_approve_decision(task: "Task") -> dict:
    return {
        "approver": "auto-approver",
        "decision": "APPROVED",
        "rationale": "auto-approved for demo (AUTO_APPROVE=true)",
        "resolution_notes": "",
    }


def interactive_cli_decision(task: "Task") -> dict:
    print(f"\n[APPROVAL REQUIRED] task={task.id} objective={task.objective} risk={task.risk_level}")
    if task.task_type == "clarification":
        print("Open ambiguities were detected. Provide answers/assumptions as resolution notes.")
    raw = input("Approve? [y/N]: ").strip().lower()
    decision = "APPROVED" if raw in ("y", "yes") else "REJECTED"
    rationale = input("Rationale: ").strip() or "(no rationale provided)"
    resolution_notes = ""
    if decision == "APPROVED" and task.task_type == "clarification":
        resolution_notes = input("Resolution notes / answers: ").strip()
    approver = input("Approver name/id: ").strip() or "unknown-approver"
    return {"approver": approver, "decision": decision, "rationale": rationale, "resolution_notes": resolution_notes}


class ApprovalManager:
    def __init__(self, decision_fn: Optional[DecisionFn] = None, auto_approve: bool = False):
        if auto_approve:
            self._decision_fn = auto_approve_decision
        else:
            self._decision_fn = decision_fn or interactive_cli_decision
        self.records: list[ApprovalRecord] = []

    def request(self, task: "Task") -> ApprovalRecord:
        requested_at = utcnow()
        outcome = self._decision_fn(task)
        record = ApprovalRecord(
            task_id=task.id,
            run_id=task.run_id,
            requested_at=requested_at,
            decided_at=utcnow(),
            approver=outcome["approver"],
            decision=outcome["decision"],
            rationale=outcome["rationale"],
            resolution_notes=outcome.get("resolution_notes", ""),
        )
        self.records.append(record)
        return record
