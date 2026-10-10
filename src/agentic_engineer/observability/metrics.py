"""Reliability metrics computed strictly from persisted audit events (never fabricated)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from .audit import AuditLog


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def compute_metrics(audit_log: AuditLog, run_id: Optional[str] = None) -> dict:
    events = audit_log.read_events(run_id) if run_id else audit_log.read_all_events()

    runs_completed = set()
    runs_succeeded = set()
    runs_with_rollback = set()
    run_started: dict[str, datetime] = {}
    run_finished: dict[str, datetime] = {}
    attempts_total = 0
    attempts_retried = 0
    failure_times: dict[str, datetime] = {}
    recoveries: list[float] = []

    for e in events:
        rid = e["run_id"]
        action, status = e["action"], e["status"]
        ts = _parse(e["timestamp"])

        if action == "run_created":
            run_started[rid] = ts
        if action == "run_completed":
            run_finished[rid] = ts
            runs_completed.add(rid)
            if status == "SUCCEEDED":
                runs_succeeded.add(rid)
        if action == "task_rolled_back":
            runs_with_rollback.add(rid)
        if action == "task_attempt":
            attempts_total += 1
        if action == "task_retry":
            attempts_retried += 1
        if action == "task_failed":
            key = f"{rid}:{e.get('task_id')}"
            failure_times[key] = ts
        if action == "task_succeeded" and e.get("task_id"):
            key = f"{rid}:{e.get('task_id')}"
            if key in failure_times:
                recoveries.append((ts - failure_times.pop(key)).total_seconds())

    completed_n = len(runs_completed)
    run_success_rate = (len(runs_succeeded) / completed_n) if completed_n else None
    retry_frequency = (attempts_retried / attempts_total) if attempts_total else None
    total_runs = len(run_started) or completed_n or None
    rollback_frequency = (len(runs_with_rollback) / total_runs) if total_runs else None

    latencies = [
        (run_finished[rid] - run_started[rid]).total_seconds()
        for rid in run_finished
        if rid in run_started
    ]
    avg_latency = sum(latencies) / len(latencies) if latencies else None
    mttr = sum(recoveries) / len(recoveries) if recoveries else None

    return {
        "note": "Prototype measurements over the observed window, not a statistically "
                "meaningful production SLO.",
        "run_success_rate": {"value": run_success_rate, "sample_size": completed_n},
        "retry_frequency": {"value": retry_frequency, "sample_size": attempts_total},
        "rollback_frequency": {"value": rollback_frequency, "sample_size": total_runs},
        "end_to_end_latency_seconds": {"value": avg_latency, "sample_size": len(latencies)},
        "mttr_seconds": {"value": mttr, "sample_size": len(recoveries)},
    }
