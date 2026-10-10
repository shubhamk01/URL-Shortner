"""The workflow engine: owns task state transitions and scheduling policy.

Agents may only propose outcomes (AgentResult); only this engine decides legal
state transitions, retries, blocking, approval pauses, and replanning.
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from pathlib import Path
from typing import Optional

from ..agents.base import AgentRegistry, AgentResult
from ..approvals.manager import ApprovalManager
from ..config import Settings
from ..observability.audit import AuditLog
from ..persistence.state_store import RunRecord, StateStore, utcnow
from ..planning.models import Task, TaskGraph, TaskState
from ..planning.planner import Planner
from ..requirements.analyzer import NormalizedRequirement


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:10]}"


class WorkflowEngine:
    def __init__(
        self,
        run: RunRecord,
        requirement: NormalizedRequirement,
        plan,
        registry: AgentRegistry,
        approval_manager: ApprovalManager,
        state_store: StateStore,
        audit_log: AuditLog,
        settings: Settings,
        planner: Optional[Planner] = None,
    ):
        self.run_record = run
        self.requirement = requirement
        self.plan = plan
        self.graph = TaskGraph(plan.tasks)
        self.registry = registry
        self.approvals = approval_manager
        self.state_store = state_store
        self.audit = audit_log
        self.settings = settings
        self.planner = planner or Planner()
        self.results: dict[str, AgentResult] = {}
        self.safe_stop_requested = False
        self._repair_attempted: set[str] = set()

    # -- public controls -------------------------------------------------

    def request_safe_stop(self) -> None:
        self.safe_stop_requested = True
        self.audit.record(self.run_record.run_id, "safe_stop_requested", actor="operator", status="INFO")

    def rollback_task(self, task_id: str) -> bool:
        """Reverses a task's own artifact writes. Only applies to FAILED tasks;
        anything the system cannot reliably reverse is left for human intervention."""
        task = self.graph.tasks[task_id]
        if task.state != TaskState.FAILED:
            return False
        artifacts_dir = self.state_store.artifacts_dir(self.run_record.run_id)
        for ref in task.output_refs:
            path = artifacts_dir / ref
            if path.exists():
                path.unlink()
        task.transition_to(TaskState.ROLLED_BACK)
        self.audit.record(self.run_record.run_id, "task_rolled_back", actor="operator", status="INFO", task_id=task.id)
        self.state_store.save_plan(self.plan)
        return True

    # -- main loop ---------------------------------------------------------

    def run(self) -> str:
        self.run_record.started_at = utcnow()
        self.audit.record(self.run_record.run_id, "run_created", actor="engine", status="INFO",
                           details={"requirement_mode": self.requirement.mode})
        self.state_store.save_run(self.run_record)
        self.state_store.save_plan(self.plan)

        with ThreadPoolExecutor(max_workers=self.settings.max_concurrency) as executor:
            while True:
                self._propagate_blocked()
                ready = [] if self.safe_stop_requested else self.graph.ready_tasks()
                if not ready:
                    break
                futures = {executor.submit(self._dispatch, task): task for task in ready}
                try:
                    futures_wait(futures.keys())
                except KeyboardInterrupt:
                    self.request_safe_stop()
                    futures_wait(futures.keys())
                self.state_store.save_plan(self.plan)

        status = self._final_status()
        self.run_record.status = status
        self.run_record.completed_at = utcnow()
        self.run_record.current_plan_id = self.plan.plan_id
        self.run_record.current_plan_version = self.plan.version
        self.state_store.save_run(self.run_record)
        self.audit.record(self.run_record.run_id, "run_completed", actor="engine",
                           status="SUCCEEDED" if status == "COMPLETED" else status,
                           details={"status": status})
        return status

    # -- dispatch ------------------------------------------------------------

    def _dispatch(self, task: Task) -> None:
        if task.state == TaskState.PENDING:
            task.transition_to(TaskState.READY)
        self.audit.record(self.run_record.run_id, "task_ready", actor="engine", status="INFO", task_id=task.id)

        if task.requires_approval and task.approval_decision is None:
            task.transition_to(TaskState.WAITING_FOR_APPROVAL)
            self.audit.record(self.run_record.run_id, "approval_requested", actor="engine", status="INFO", task_id=task.id)
            record = self.approvals.request(task)
            task.approval_decision = record.to_dict()
            self.audit.record(self.run_record.run_id, "approval_decided", actor=record.approver,
                               status=record.decision, task_id=task.id,
                               details={"rationale": record.rationale})
            if record.decision == "REJECTED":
                task.transition_to(TaskState.CANCELLED)
                self.audit.record(self.run_record.run_id, "task_cancelled", actor="engine", status="INFO", task_id=task.id)
                return
            task.transition_to(TaskState.RUNNING)
        else:
            task.transition_to(TaskState.RUNNING)

        task.attempt_count += 1
        task.started_at = utcnow()
        self.audit.record(self.run_record.run_id, "task_attempt", actor="engine", status="INFO", task_id=task.id,
                           details={"attempt": task.attempt_count})

        try:
            agent = self.registry.get(task.task_type)
            result = agent.execute(task, self._build_context())
        except Exception as exc:  # noqa: BLE001 - agent failures must not crash the engine
            result = AgentResult(success=False, error_summary=str(exc), retryable=True)

        self.results[task.id] = result
        task.finished_at = utcnow()
        task.output_refs = result.output_refs

        if result.success:
            task.transition_to(TaskState.SUCCEEDED)
            self.audit.record(self.run_record.run_id, "task_succeeded", actor=task.task_type, status="SUCCEEDED",
                               task_id=task.id, details={"output_refs": result.output_refs})
            if task.task_type == "clarification":
                self._replan_after_clarification(task)
            return

        task.error_summary = result.error_summary
        self.audit.record(self.run_record.run_id, "task_failed", actor=task.task_type, status="FAILED",
                           task_id=task.id, details={"error": result.error_summary})
        task.transition_to(TaskState.FAILED)

        if task.retryable and result.retryable and task.attempt_count < task.max_attempts:
            task.transition_to(TaskState.RETRYING)
            self.audit.record(self.run_record.run_id, "task_retry", actor="engine", status="INFO", task_id=task.id,
                               details={"attempt": task.attempt_count})
            task.transition_to(TaskState.READY)
            return

        self._attempt_repair_or_block(task)

    def _attempt_repair_or_block(self, task: Task) -> None:
        is_repair = task.context.get("_is_repair", False)
        if not is_repair and task.id not in self._repair_attempted:
            self._repair_attempted.add(task.id)
            repair = self.planner.create_repair_task(task, attempt_suffix=1)
            repair.context["_is_repair"] = True
            self.graph.tasks[repair.id] = repair
            for other in self.graph.tasks.values():
                if task.id in other.depends_on and other.id != repair.id:
                    other.depends_on = [repair.id if d == task.id else d for d in other.depends_on]
            task.transition_to(TaskState.BLOCKED)
            self.audit.record(self.run_record.run_id, "task_repair_created", actor="engine", status="INFO",
                               task_id=task.id, details={"repair_task_id": repair.id})
            self.plan.tasks = self.graph.tasks
            self.state_store.save_plan(self.plan)
        else:
            task.transition_to(TaskState.BLOCKED)
            self.audit.record(self.run_record.run_id, "task_blocked", actor="engine", status="INFO", task_id=task.id)

    def _propagate_blocked(self) -> None:
        changed = True
        while changed:
            changed = False
            for task in self.graph.tasks.values():
                if task.state == TaskState.PENDING and self.graph.any_dependency_blocked(task):
                    task.transition_to(TaskState.BLOCKED)
                    self.audit.record(self.run_record.run_id, "task_blocked", actor="engine", status="INFO",
                                       task_id=task.id, details={"reason": "upstream dependency blocked"})
                    changed = True

    def _replan_after_clarification(self, clarification_task: Task) -> None:
        decision = clarification_task.approval_decision or {}
        resolution_notes = decision.get("resolution_notes", "") or "no additional detail provided"
        new_plan = self.planner.replan_after_clarification(self.plan, self.requirement, resolution_notes)
        self.plan = new_plan
        self.graph = TaskGraph(new_plan.tasks)
        self.state_store.save_plan(new_plan)
        self.audit.record(self.run_record.run_id, "plan_revised", actor="engine", status="INFO",
                           details={"new_plan_id": new_plan.plan_id, "version": new_plan.version,
                                    "parent_plan_id": new_plan.parent_plan_id, "rationale": new_plan.rationale})

    def _build_context(self) -> dict:
        return {
            "run_id": self.run_record.run_id,
            "plan_id": self.plan.plan_id,
            "plan_version": self.plan.version,
            "requirement": self.requirement,
            "artifacts_dir": self.state_store.artifacts_dir(self.run_record.run_id),
            "results": self.results,
            "timeout_seconds": self.settings.task_timeout_seconds,
        }

    def _final_status(self) -> str:
        if self.safe_stop_requested and not self.graph.all_succeeded():
            return "STOPPED"
        bad_states = {TaskState.BLOCKED, TaskState.CANCELLED, TaskState.FAILED}
        if any(t.state in bad_states for t in self.graph.tasks.values()):
            return "FAILED"
        if self.graph.all_succeeded():
            return "COMPLETED"
        return "INCOMPLETE"
