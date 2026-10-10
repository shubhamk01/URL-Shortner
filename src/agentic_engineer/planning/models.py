"""Task graph data model shared by the planner and the orchestration engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"
    SKIPPED = "SKIPPED"


TERMINAL_STATES = {
    TaskState.SUCCEEDED,
    TaskState.CANCELLED,
    TaskState.ROLLED_BACK,
    TaskState.SKIPPED,
}

# Legal state transitions, enforced centrally by the workflow engine rather than
# left to individual agents.
_ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.READY, TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.READY: {TaskState.RUNNING, TaskState.WAITING_FOR_APPROVAL, TaskState.CANCELLED, TaskState.BLOCKED},
    TaskState.WAITING_FOR_APPROVAL: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.BLOCKED},
    TaskState.RUNNING: {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.FAILED: {TaskState.RETRYING, TaskState.BLOCKED, TaskState.ROLLED_BACK, TaskState.CANCELLED},
    TaskState.RETRYING: {TaskState.READY, TaskState.RUNNING},
    TaskState.BLOCKED: {TaskState.READY, TaskState.SKIPPED, TaskState.CANCELLED},
    TaskState.SUCCEEDED: set(),
    TaskState.CANCELLED: set(),
    TaskState.ROLLED_BACK: {TaskState.READY},
    TaskState.SKIPPED: set(),
}


class IllegalTransitionError(Exception):
    pass


@dataclass
class Task:
    id: str
    run_id: str
    task_type: str
    objective: str
    depends_on: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    risk_level: str = "low"  # low | medium | high
    requires_approval: bool = False
    retryable: bool = True
    max_attempts: int = 3

    state: TaskState = TaskState.PENDING
    attempt_count: int = 0
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_summary: Optional[str] = None
    agent_id: Optional[str] = None
    approval_decision: Optional[dict] = None
    parent_task_id: Optional[str] = None
    plan_version: int = 1
    output_refs: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    def can_transition_to(self, new_state: TaskState) -> bool:
        return new_state in _ALLOWED_TRANSITIONS.get(self.state, set())

    def transition_to(self, new_state: TaskState) -> None:
        if not self.can_transition_to(new_state):
            raise IllegalTransitionError(f"cannot transition task {self.id} from {self.state} to {new_state}")
        self.state = new_state
        self.updated_at = utcnow()

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["state"] = self.state.value
        for key in ("created_at", "updated_at", "started_at", "finished_at"):
            value = d[key]
            d[key] = value.isoformat() if value else None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        data = dict(data)
        data["state"] = TaskState(data["state"])
        for key in ("created_at", "updated_at", "started_at", "finished_at"):
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)


@dataclass
class PlanVersion:
    plan_id: str
    run_id: str
    version: int
    tasks: dict[str, Task]
    parent_plan_id: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "run_id": self.run_id,
            "version": self.version,
            "parent_plan_id": self.parent_plan_id,
            "created_at": self.created_at.isoformat(),
            "rationale": self.rationale,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanVersion":
        tasks = {tid: Task.from_dict(t) for tid, t in data["tasks"].items()}
        return cls(
            plan_id=data["plan_id"],
            run_id=data["run_id"],
            version=data["version"],
            parent_plan_id=data.get("parent_plan_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            rationale=data.get("rationale", ""),
            tasks=tasks,
        )


class TaskGraph:
    """Dependency graph view over a plan's tasks."""

    def __init__(self, tasks: dict[str, Task]):
        self.tasks = tasks

    def dependencies_succeeded(self, task: Task) -> bool:
        return all(self.tasks[dep].state == TaskState.SUCCEEDED for dep in task.depends_on)

    def any_dependency_blocked(self, task: Task) -> bool:
        blocking = {TaskState.BLOCKED, TaskState.FAILED, TaskState.CANCELLED}
        return any(self.tasks[dep].state in blocking for dep in task.depends_on)

    def ready_tasks(self) -> list[Task]:
        """PENDING tasks are first-time candidates; READY tasks are re-queued retries."""
        ready = []
        for task in self.tasks.values():
            if task.state in (TaskState.PENDING, TaskState.READY) and self.dependencies_succeeded(task):
                ready.append(task)
        return ready

    def descendants_of(self, task_id: str) -> list[str]:
        """Returns all task IDs that (transitively) depend on the given task."""
        result: list[str] = []
        frontier = [task_id]
        seen = {task_id}
        while frontier:
            current = frontier.pop()
            for t in self.tasks.values():
                if current in t.depends_on and t.id not in seen:
                    seen.add(t.id)
                    result.append(t.id)
                    frontier.append(t.id)
        return result

    def is_complete(self) -> bool:
        return all(t.state in TERMINAL_STATES or t.state == TaskState.FAILED for t in self.tasks.values())

    def all_succeeded(self) -> bool:
        return all(t.state == TaskState.SUCCEEDED for t in self.tasks.values())
