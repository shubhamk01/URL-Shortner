"""Human-readable run report rendering (used by the CLI `inspect` command)."""
from __future__ import annotations

from ..observability.audit import AuditLog
from ..persistence.state_store import RunRecord, StateStore


def render_run_report(run_id: str, state_store: StateStore, audit_log: AuditLog) -> str:
    run = state_store.load_run(run_id)
    plan = state_store.load_plan(run_id)
    lines = [
        f"Run: {run.run_id}  status={run.status}  mode={run.mode}",
        f"Requirement: {run.requirement_text}",
        f"Plan: {plan.plan_id} v{plan.version}"
        + (f" (parent={plan.parent_plan_id})" if plan.parent_plan_id else ""),
        "",
        "Tasks:",
    ]
    for task in plan.tasks.values():
        deps = ",".join(task.depends_on) or "-"
        approval = ""
        if task.approval_decision:
            approval = f" approval={task.approval_decision['decision']} by {task.approval_decision['approver']}"
        lines.append(f"  [{task.state.value:>20}] {task.id:<22} deps=({deps}){approval}")
    lines.append("")
    lines.append("Recent audit events:")
    for event in audit_log.read_events(run_id)[-20:]:
        lines.append(f"  {event['timestamp']} {event['action']:<20} task={event.get('task_id')} status={event['status']}")
    return "\n".join(lines)
