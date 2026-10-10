"""Orchestration engine tests using lightweight fake agents (no real pytest subprocess),
so these tests stay fast and fully deterministic.
"""
from __future__ import annotations

import threading
import time

import pytest

from agentic_engineer.agents.base import AgentRegistry, AgentResult
from agentic_engineer.approvals.manager import ApprovalManager
from agentic_engineer.config import Settings
from agentic_engineer.observability.audit import AuditLog
from agentic_engineer.observability.metrics import compute_metrics
from agentic_engineer.persistence.state_store import RunRecord, StateStore
from agentic_engineer.planning.models import PlanVersion, Task, TaskState
from agentic_engineer.planning.planner import Planner
from agentic_engineer.requirements.analyzer import NormalizedRequirement
from agentic_engineer.orchestration.engine import WorkflowEngine


class FakeAgent:
    """Records calls; behavior is scripted via a callable or fixed outcomes list."""

    def __init__(self, behavior=None, on_call=None, sleep_seconds: float = 0.0):
        self._behavior = behavior or (lambda call_count: AgentResult(success=True, output_refs=[]))
        self.calls: list = []
        self._on_call = on_call
        self._sleep_seconds = sleep_seconds

    def execute(self, task, context) -> AgentResult:
        self.calls.append(task.id)
        if self._on_call:
            self._on_call(task, context)
        if self._sleep_seconds:
            time.sleep(self._sleep_seconds)
        return self._behavior(len(self.calls))


def make_settings(tmp_path, max_concurrency=3, max_task_attempts=3, auto_approve=True):
    return Settings(
        database_path=str(tmp_path / "unused.db"),
        allowed_url_schemes=("http", "https"),
        short_code_length=7,
        short_code_max_collision_attempts=5,
        runs_dir=str(tmp_path / "runs"),
        max_concurrency=max_concurrency,
        max_task_attempts=max_task_attempts,
        task_timeout_seconds=30,
        run_budget_seconds=300,
        auto_approve=auto_approve,
        ai_provider="mock",
        ai_api_key="",
    )


def make_engine(tmp_path, tasks: dict[str, Task], registry: AgentRegistry, settings=None, decision_fn=None):
    settings = settings or make_settings(tmp_path)
    state_store = StateStore(settings.runs_dir)
    audit_log = AuditLog(settings.runs_dir)
    approvals = ApprovalManager(decision_fn=decision_fn, auto_approve=settings.auto_approve)
    requirement = NormalizedRequirement(original_text="test", mode="greenfield", summary="s")
    run = RunRecord(run_id="run-test", requirement_text="test", mode="greenfield")
    plan = PlanVersion(plan_id="plan-test", run_id="run-test", version=1, tasks=tasks)
    return WorkflowEngine(
        run=run, requirement=requirement, plan=plan, registry=registry,
        approval_manager=approvals, state_store=state_store, audit_log=audit_log,
        settings=settings, planner=Planner(),
    )


def task(id_, deps=None, **kwargs):
    return Task(id=id_, run_id="run-test", task_type=kwargs.pop("task_type", id_), objective=f"do {id_}",
                depends_on=deps or [], **kwargs)


def test_dependency_blocks_until_prereq_succeeds(tmp_path):
    agent_a = FakeAgent()
    agent_b = FakeAgent()
    registry = AgentRegistry()
    registry.register("a", agent_a)
    registry.register("b", agent_b)
    tasks = {"A": task("A", task_type="a"), "B": task("B", deps=["A"], task_type="b")}
    engine = make_engine(tmp_path, tasks, registry)
    status = engine.run()
    assert status == "COMPLETED"
    assert agent_a.calls == ["A"]
    assert agent_b.calls == ["B"]
    assert tasks["A"].finished_at <= tasks["B"].started_at


def test_independent_tasks_run_concurrently(tmp_path):
    starts: dict[str, float] = {}

    def record_start(t, ctx):
        starts[t.id] = time.monotonic()

    agent_a = FakeAgent(on_call=record_start, sleep_seconds=0.3)
    agent_b = FakeAgent(on_call=record_start, sleep_seconds=0.3)
    registry = AgentRegistry()
    registry.register("a", agent_a)
    registry.register("b", agent_b)
    tasks = {"A": task("A", task_type="a"), "B": task("B", task_type="b")}
    engine = make_engine(tmp_path, tasks, registry, settings=make_settings(tmp_path, max_concurrency=2))
    start = time.monotonic()
    status = engine.run()
    elapsed = time.monotonic() - start
    assert status == "COMPLETED"
    # Both start within a tight window of each other (genuine parallelism) rather than
    # asserting a strict wall-clock bound, which is flaky under shared-machine load.
    assert abs(starts["A"] - starts["B"]) < 0.2
    assert elapsed < 1.5  # generous upper bound; sequential execution would exceed this


def test_synchronization_barrier_waits_for_all_parallel_branches(tmp_path):
    registry = AgentRegistry()
    registry.register("root", FakeAgent())
    registry.register("branch", FakeAgent(sleep_seconds=0.1))
    registry.register("sync", FakeAgent())
    tasks = {
        "root": task("root", task_type="root"),
        "b1": task("b1", deps=["root"], task_type="branch"),
        "b2": task("b2", deps=["root"], task_type="branch"),
        "sync": task("sync", deps=["b1", "b2"], task_type="sync"),
    }
    engine = make_engine(tmp_path, tasks, registry, settings=make_settings(tmp_path, max_concurrency=2))
    status = engine.run()
    assert status == "COMPLETED"
    assert tasks["sync"].started_at >= tasks["b1"].finished_at
    assert tasks["sync"].started_at >= tasks["b2"].finished_at


def test_transient_failure_retries_up_to_configured_limit(tmp_path):
    def flaky(call_count):
        if call_count < 3:
            return AgentResult(success=False, error_summary="transient", retryable=True)
        return AgentResult(success=True)

    agent = FakeAgent(behavior=flaky)
    registry = AgentRegistry()
    registry.register("flaky", agent)
    tasks = {"A": task("A", task_type="flaky", max_attempts=3)}
    engine = make_engine(tmp_path, tasks, registry)
    status = engine.run()
    assert status == "COMPLETED"
    assert tasks["A"].attempt_count == 3
    assert len(agent.calls) == 3


def test_non_retryable_failure_blocks_and_creates_bounded_repair(tmp_path):
    agent = FakeAgent(behavior=lambda n: AgentResult(success=False, error_summary="boom", retryable=False))
    registry = AgentRegistry()
    registry.register("always_fail", agent)
    tasks = {
        "A": task("A", task_type="always_fail", max_attempts=1),
        "B": task("B", deps=["A"], task_type="always_fail"),
    }
    engine = make_engine(tmp_path, tasks, registry)
    status = engine.run()
    assert status == "FAILED"
    assert tasks["A"].state == TaskState.BLOCKED
    # exactly one bounded repair task was created, took over B's dependency, and also failed
    repair_ids = [tid for tid in engine.graph.tasks if tid.startswith("A-repair-")]
    assert len(repair_ids) == 1
    assert engine.graph.tasks[repair_ids[0]].state == TaskState.BLOCKED
    assert tasks["B"].depends_on == repair_ids
    assert tasks["B"].state == TaskState.BLOCKED


def test_approval_rejection_prevents_the_gated_action(tmp_path):
    agent = FakeAgent()
    registry = AgentRegistry()
    registry.register("design", agent)
    registry.register("after", FakeAgent())
    tasks = {
        "design": task("design", task_type="design", requires_approval=True),
        "after": task("after", deps=["design"], task_type="after"),
    }

    def reject(_task):
        return {"approver": "reviewer", "decision": "REJECTED", "rationale": "not ready", "resolution_notes": ""}

    engine = make_engine(tmp_path, tasks, registry, settings=make_settings(tmp_path, auto_approve=False),
                          decision_fn=reject)
    status = engine.run()
    assert status == "FAILED"
    assert agent.calls == []  # the gated action never executed
    assert tasks["design"].state == TaskState.CANCELLED
    assert tasks["after"].state == TaskState.BLOCKED


def test_safe_stop_prevents_new_tasks_from_starting(tmp_path):
    registry = AgentRegistry()
    tasks = {"A": task("A", task_type="a"), "B": task("B", deps=["A"], task_type="b")}

    engine_holder = {}

    def stop_after_a(t, ctx):
        engine_holder["engine"].request_safe_stop()

    registry.register("a", FakeAgent(on_call=stop_after_a))
    registry.register("b", FakeAgent())
    engine = make_engine(tmp_path, tasks, registry)
    engine_holder["engine"] = engine
    status = engine.run()
    assert status == "STOPPED"
    assert tasks["A"].state == TaskState.SUCCEEDED
    assert tasks["B"].state == TaskState.PENDING  # never scheduled


def test_failed_validation_blocks_release_readiness(tmp_path):
    registry = AgentRegistry()
    registry.register("test", FakeAgent(behavior=lambda n: AgentResult(success=False, retryable=False)))
    registry.register("release_readiness", FakeAgent())
    tasks = {
        "test_unit": task("test_unit", task_type="test", max_attempts=1),
        "release_readiness": task("release_readiness", deps=["test_unit"], task_type="release_readiness"),
    }
    engine = make_engine(tmp_path, tasks, registry)
    status = engine.run()
    assert status == "FAILED"
    assert tasks["release_readiness"].state == TaskState.BLOCKED


def test_audit_records_exist_for_attempts_and_completion(tmp_path):
    registry = AgentRegistry()
    registry.register("a", FakeAgent())
    tasks = {"A": task("A", task_type="a")}
    engine = make_engine(tmp_path, tasks, registry)
    engine.run()
    actions = {e["action"] for e in engine.audit.read_events("run-test")}
    assert {"run_created", "task_attempt", "task_succeeded", "run_completed"} <= actions


def test_rollback_reverses_a_failed_tasks_artifact_writes(tmp_path):
    settings = make_settings(tmp_path)
    artifacts_dir = StateStore(settings.runs_dir).artifacts_dir("run-test")
    written = artifacts_dir / "bad_output.txt"

    def write_then_fail(n):
        written.write_text("partial output")
        return AgentResult(success=False, output_refs=["bad_output.txt"], retryable=False)

    registry = AgentRegistry()
    registry.register("a", FakeAgent(behavior=write_then_fail))
    tasks = {"A": task("A", task_type="a", max_attempts=1)}
    engine = make_engine(tmp_path, tasks, registry, settings=settings)
    engine.run()
    assert written.exists()
    # the failed task's own state before any auto-repair bookkeeping overwrote it:
    original = engine.graph.tasks["A"]
    original.state = TaskState.FAILED  # force back for this manual-rollback demonstration
    assert engine.rollback_task("A") is True
    assert not written.exists()
    assert original.state == TaskState.ROLLED_BACK


def test_metrics_are_computed_from_recorded_events_not_fabricated(tmp_path):
    settings = make_settings(tmp_path)
    registry = AgentRegistry()
    registry.register("a", FakeAgent())
    tasks = {"A": task("A", task_type="a")}
    engine = make_engine(tmp_path, tasks, registry, settings=settings)
    engine.run()
    metrics = compute_metrics(engine.audit, run_id="run-test")
    assert metrics["run_success_rate"]["sample_size"] == 1
    assert metrics["run_success_rate"]["value"] == 1.0


def test_replanning_preserves_succeeded_tasks_and_links_lineage():
    from agentic_engineer.requirements.analyzer import RequirementAnalyzer

    requirement = RequirementAnalyzer().analyze("Make links safer and track usage.")
    planner = Planner()
    plan_v1 = planner.create_plan("run-amb", requirement)
    for tid in ("intake", "understand", "clarification_gate"):
        plan_v1.tasks[tid].state = TaskState.SUCCEEDED

    plan_v2 = planner.replan_after_clarification(plan_v1, requirement, "only allow http/https, retain 30 days")
    assert plan_v2.version == 2
    assert plan_v2.parent_plan_id == plan_v1.plan_id
    assert plan_v2.tasks["intake"] is plan_v1.tasks["intake"]  # preserved, not re-run
    assert plan_v2.tasks["design"].state == TaskState.PENDING  # regenerated
    assert any("only allow http/https" in c for c in plan_v2.tasks["design"].acceptance_criteria)


def test_all_scenario_plans_gate_release_and_include_operations_handoff():
    from agentic_engineer.requirements.analyzer import RequirementAnalyzer

    analyzer = RequirementAnalyzer()
    requirements = [
        analyzer.analyze("Create a URL shortener."),
        analyzer.analyze("Add analytics to existing URLs without breaking redirects."),
        analyzer.analyze("Make links safer and track usage."),
    ]
    planner = Planner()

    for index, requirement in enumerate(requirements):
        plan = planner.create_plan(f"run-sdlc-{index}", requirement)
        release_gate = plan.tasks["release_approval"]
        assert release_gate.requires_approval is True
        assert release_gate.depends_on == ["release_readiness"]
        assert plan.tasks["operations_handoff"].depends_on == ["release_approval"]
        assert plan.tasks["summarize"].depends_on == ["operations_handoff"]


def test_rejected_release_candidate_blocks_operations_handoff(tmp_path):
    release_agent = FakeAgent()
    operations_agent = FakeAgent()
    registry = AgentRegistry()
    registry.register("release_readiness", FakeAgent())
    registry.register("release_approval", release_agent)
    registry.register("operations_handoff", operations_agent)
    tasks = {
        "release_readiness": task("release_readiness", task_type="release_readiness"),
        "release_approval": task(
            "release_approval", deps=["release_readiness"],
            task_type="release_approval", requires_approval=True,
        ),
        "operations_handoff": task(
            "operations_handoff", deps=["release_approval"], task_type="operations_handoff",
        ),
    }

    def reject_release(_task):
        return {
            "approver": "release-reviewer",
            "decision": "REJECTED",
            "rationale": "release conditions not met",
            "resolution_notes": "",
        }

    engine = make_engine(
        tmp_path, tasks, registry,
        settings=make_settings(tmp_path, auto_approve=False),
        decision_fn=reject_release,
    )
    assert engine.run() == "FAILED"
    assert release_agent.calls == []
    assert operations_agent.calls == []
    assert tasks["release_approval"].state == TaskState.CANCELLED
    assert tasks["operations_handoff"].state == TaskState.BLOCKED


def test_release_manifest_and_operations_handoff_do_not_claim_deployment(tmp_path):
    import json

    from agentic_engineer.agents.mock_agents import OperationsHandoffAgent, ReleaseApprovalAgent

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    context = {
        "run_id": "run-release",
        "plan_id": "plan-release",
        "plan_version": 2,
        "artifacts_dir": artifacts_dir,
    }
    release_task = task("release_approval", task_type="release_approval")
    release_task.approval_decision = {
        "decision": "APPROVED",
        "approver": "reviewer",
        "decided_at": "2026-10-10T00:00:00+00:00",
        "rationale": "checks reviewed",
    }

    release_result = ReleaseApprovalAgent().execute(release_task, context)
    manifest = json.loads((artifacts_dir / "release_manifest.json").read_text(encoding="utf-8"))
    assert release_result.success is True
    assert manifest["release_state"] == "APPROVED_CANDIDATE"
    assert manifest["deployment_state"] == "NOT_DEPLOYED"

    operations_result = OperationsHandoffAgent().execute(
        task("operations_handoff", task_type="operations_handoff"), context
    )
    runbook = (artifacts_dir / "operations_runbook.md").read_text(encoding="utf-8")
    assert operations_result.success is True
    assert "Status: NOT DEPLOYED" in runbook
