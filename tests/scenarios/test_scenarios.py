"""End-to-end scenario tests: greenfield, brownfield, and ambiguous requirements,
run through the real pipeline (real agents, real pytest-based validation).
These are slower than the orchestrator unit tests because they genuinely execute
the project's test suite as part of the "test" tasks.
"""
from __future__ import annotations

import json

from agentic_engineer.config import Settings
from agentic_engineer.orchestration.pipeline import run_requirement


def make_settings(tmp_path, auto_approve=True):
    return Settings(
        database_path=str(tmp_path / "unused.db"),
        allowed_url_schemes=("http", "https"),
        short_code_length=7,
        short_code_max_collision_attempts=5,
        runs_dir=str(tmp_path / "runs"),
        max_concurrency=3,
        max_task_attempts=2,
        task_timeout_seconds=120,
        run_budget_seconds=600,
        auto_approve=auto_approve,
        ai_provider="mock",
        ai_api_key="",
    )


def _artifact(engine, name: str) -> str:
    path = engine.state_store.artifacts_dir(engine.run_record.run_id) / name
    assert path.exists(), f"expected artifact missing: {name}"
    return path.read_text(encoding="utf-8")


def _assert_release_handoff(engine) -> None:
    manifest = json.loads(_artifact(engine, "release_manifest.json"))
    assert manifest["release_state"] == "APPROVED_CANDIDATE"
    assert manifest["deployment_state"] == "NOT_DEPLOYED"
    assert engine.graph.tasks["release_approval"].approval_decision["decision"] == "APPROVED"
    assert "Status: NOT DEPLOYED" in _artifact(engine, "operations_runbook.md")


def test_greenfield_scenario_completes_with_expected_artifacts(tmp_path):
    outcome = run_requirement(
        "Create a URL shortener with click analytics.",
        settings=make_settings(tmp_path),
    )
    assert outcome.status == "COMPLETED"
    engine = outcome.engine
    _artifact(engine, "design.md")
    _artifact(engine, "implementation_notes.md")
    _artifact(engine, "generated_docs.md")
    readiness = json.loads(_artifact(engine, "readiness.json"))
    assert readiness["go_no_go"] == "GO"
    assert readiness["scope"] == "release_candidate_only"
    assert readiness["deployment_authorized"] is False
    _assert_release_handoff(engine)
    _artifact(engine, "summary.md")
    assert engine.graph.tasks["design"].approval_decision["decision"] == "APPROVED"


def test_brownfield_scenario_preserves_redirect_and_adds_analytics(tmp_path):
    outcome = run_requirement(
        "Add analytics to existing short URLs without breaking redirection.",
        settings=make_settings(tmp_path),
    )
    assert outcome.status == "COMPLETED"
    engine = outcome.engine
    _artifact(engine, "impact_analysis.md")
    diff = _artifact(engine, "diff.md")
    assert "redirect contract" in diff.lower()
    readiness = json.loads(_artifact(engine, "readiness.json"))
    assert readiness["go_no_go"] == "GO"
    _assert_release_handoff(engine)


def test_ambiguous_scenario_requires_clarification_then_replans(tmp_path):
    resolution_text = (
        "Only allow http/https destinations; store click counts and timestamps "
        "only (no IP); retain 30 days."
    )

    def answer_clarification(task):
        resolution = resolution_text if task.id == "clarification_gate" else ""
        return {
            "approver": "demo-reviewer",
            "decision": "APPROVED",
            "rationale": "approved for scenario demo",
            "resolution_notes": resolution,
        }

    outcome = run_requirement(
        "Make links safer and track usage.",
        settings=make_settings(tmp_path, auto_approve=False),
        decision_fn=answer_clarification,
    )
    assert outcome.status == "COMPLETED"
    engine = outcome.engine

    # Replanning happened: the executed plan is version 2, linked back to version 1.
    assert engine.plan.version == 2
    assert engine.plan.parent_plan_id is not None

    clarification = json.loads(_artifact(engine, "clarification.json"))
    assert clarification["resolution_notes"] == resolution_text
    assert clarification["ambiguities"]  # at least one ambiguity was detected

    design = _artifact(engine, "design.md")
    assert resolution_text in design

    readiness = json.loads(_artifact(engine, "readiness.json"))
    assert readiness["go_no_go"] == "GO"
    _assert_release_handoff(engine)
