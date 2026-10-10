"""High-level entry point: requirement text -> fully executed run.

Wires together the requirement analyzer, planner, agent registry, approval
manager, state store, audit log, and workflow engine. Used by both the CLI and
the scenario tests so there is exactly one orchestration wiring path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..agents.base import AgentRegistry
from ..agents.mock_agents import build_default_registry
from ..approvals.manager import ApprovalManager, DecisionFn
from ..config import Settings, get_settings
from ..model import resolve_adapter
from ..observability.audit import AuditLog
from ..persistence.state_store import RunRecord, StateStore
from ..planning.planner import Planner
from ..requirements.analyzer import NormalizedRequirement, RequirementAnalyzer
from .engine import WorkflowEngine, new_run_id


@dataclass
class RunOutcome:
    run_id: str
    status: str
    engine: WorkflowEngine


def run_requirement(
    requirement_text: str,
    settings: Optional[Settings] = None,
    decision_fn: Optional[DecisionFn] = None,
    registry: Optional[AgentRegistry] = None,
) -> RunOutcome:
    settings = settings or get_settings()
    state_store = StateStore(settings.runs_dir)
    audit_log = AuditLog(settings.runs_dir)
    registry = registry or build_default_registry(model=resolve_adapter(settings))
    approvals = ApprovalManager(decision_fn=decision_fn, auto_approve=settings.auto_approve)
    planner = Planner()

    requirement: NormalizedRequirement = RequirementAnalyzer().analyze(requirement_text)
    run_id = new_run_id()
    run = RunRecord(run_id=run_id, requirement_text=requirement_text, mode=requirement.mode)
    plan = planner.create_plan(run_id, requirement)

    engine = WorkflowEngine(
        run=run,
        requirement=requirement,
        plan=plan,
        registry=registry,
        approval_manager=approvals,
        state_store=state_store,
        audit_log=audit_log,
        settings=settings,
        planner=planner,
    )
    status = engine.run()
    return RunOutcome(run_id=run_id, status=status, engine=engine)
