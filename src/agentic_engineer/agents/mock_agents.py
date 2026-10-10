"""Agents, mapped onto the four requested roles (Planner/Developer/Tester/
Documentation) plus small orchestration-bookkeeping agents (intake, understand,
impact analysis, clarification, release readiness, summarize).

Every role agent uses the configured ModelAdapter (Copilot by default; mock
for explicit offline/testing runs) for an additional, clearly-labeled
AI-assisted narrative. Model
failures (auth/timeout/unavailable/empty-response) never fail the task — they
are caught and recorded, and the deterministic output is used regardless. The
Tester role is the one agent whose core output is NOT model-derived: it
genuinely executes the project's pytest suite via validation.runner, so
validation evidence in the audit trail is real, and it clearly separates any
model-*proposed* tests from the actually-*executed* test report.

Distinct permissions by construction: only the Tester role imports
validation.runner (the only agent allowed to execute a subprocess); the
Developer role only ever *proposes* changes/writes notes and never claims code
was applied; all agents write exclusively inside the run's sandboxed
artifacts directory (policies.guardrails.validate_output_path).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..model.adapter import ModelAdapter, ModelError
from ..model.mock_adapter import MockModelAdapter
from ..policies.guardrails import validate_output_path
from ..validation.runner import run_tests
from .base import Agent, AgentResult


def _write(artifacts_dir: Path, relpath: str, content: str) -> str:
    path = validate_output_path(relpath, artifacts_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return relpath


def _model_assist(model: ModelAdapter, role: str, prompt: str, timeout_seconds: float) -> Optional[str]:
    """Best-effort model call. Returns labeled content, or None if the model is
    unavailable/unconfigured/erroring — callers must keep working without it."""
    if isinstance(model, MockModelAdapter):
        return None
    try:
        response = model.complete(prompt, role=role, timeout_seconds=timeout_seconds)
        return response.content
    except ModelError:
        return None


class IntakeAgent(Agent):
    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        ref = _write(
            context["artifacts_dir"], "requirement.json",
            json.dumps({"run_id": context["run_id"], **requirement.to_dict()}, indent=2),
        )
        return AgentResult(success=True, output_refs=[ref])


class UnderstandAgent(Agent):
    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        ref = _write(
            context["artifacts_dir"], "normalized_requirement.json",
            json.dumps(requirement.to_dict(), indent=2),
        )
        details = {"ambiguities": requirement.ambiguities, "mode": requirement.mode}
        return AgentResult(success=True, output_refs=[ref], details=details)


class DesignAgent(Agent):
    """Planner role: interprets the requirement into a design, folding in any
    clarified/assumed decisions. Optionally model-assisted (ambiguity framing)."""

    role = "planner"

    def __init__(self, model: Optional[ModelAdapter] = None):
        self.model = model or MockModelAdapter()

    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        criteria = task.acceptance_criteria or requirement.acceptance_criteria
        lines = [
            f"# Design — {context['run_id']}",
            "",
            f"Mode: **{requirement.mode}**",
            "",
            "## API",
            "- POST /api/urls — create a short URL",
            "- GET /r/{code} — redirect",
            "- GET /api/urls/{code} — metadata",
            "- GET /api/urls/{code}/analytics — click analytics",
            "",
            "## Data model",
            "- ShortURL(id, code, original_url, created_at, expires_at, is_active)",
            "- ClickEvent(id, code, clicked_at, referrer, user_agent)",
            "",
            "## Acceptance criteria",
            *[f"- {c}" for c in criteria],
        ]
        if task.approval_decision and task.approval_decision.get("resolution_notes"):
            lines += ["", "## Clarified decisions", f"- {task.approval_decision['resolution_notes']}"]
        assist = _model_assist(
            self.model, self.role,
            f"Review this URL-shortener design for requirement '{requirement.original_text}' "
            f"and flag any remaining ambiguity or risk:\n" + "\n".join(lines),
            context.get("timeout_seconds", 30),
        )
        if assist:
            lines += ["", "## AI-assisted review (not authoritative)", assist]
        ref = _write(context["artifacts_dir"], "design.md", "\n".join(lines))
        return AgentResult(success=True, output_refs=[ref])


class ImplementAgent(Agent):
    """Developer role: proposes code changes and points at the real, already-working
    url_shortener source as the artifact of record (see tradeoffs-and-limitations.md
    for why agents do not mutate the orchestrator's own source tree live). Never
    claims a change has been applied — only ever describes a proposal."""

    role = "developer"

    def __init__(self, model: Optional[ModelAdapter] = None):
        self.model = model or MockModelAdapter()

    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        notes = [
            f"# Implementation notes (PROPOSED, not applied) — {context['run_id']}",
            "",
            "Proposed target modules (`src/agentic_engineer/url_shortener/` and `src/agentic_engineer/api/`):",
            "- `service.py`: URL validation (scheme allow-list), short-code creation with",
            "  bounded collision retries, redirect resolution, best-effort click recording.",
            "- `repository.py`: parameterized SQLite access for ShortURL and ClickEvent.",
            "- `api/app.py`: POST /api/urls, GET /r/{code}, GET /api/urls/{code},",
            "  GET /api/urls/{code}/analytics, GET /health.",
        ]
        assist = _model_assist(
            self.model, self.role,
            f"Propose (do not apply) the code changes needed for: {requirement.original_text}",
            context.get("timeout_seconds", 30),
        )
        if assist:
            notes += ["", "## AI-proposed change (not applied)", assist]
        if requirement.mode == "brownfield":
            diff = [
                "# Change diff summary (PROPOSED, not applied)",
                "",
                "- No change to the GET /r/{code} redirect contract (still 307 to original_url).",
                "- Click analytics already recorded via `URLShortenerService.record_click`,",
                "  wrapped in try/except so analytics failures cannot break redirection.",
                "- New: GET /api/urls/{code}/analytics exposes click_count and recent_clicks.",
            ]
            diff_ref = _write(context["artifacts_dir"], "diff.md", "\n".join(diff))
            notes_ref = _write(context["artifacts_dir"], "implementation_notes.md", "\n".join(notes))
            return AgentResult(success=True, output_refs=[notes_ref, diff_ref])
        notes_ref = _write(context["artifacts_dir"], "implementation_notes.md", "\n".join(notes))
        return AgentResult(success=True, output_refs=[notes_ref])


class TestAgent(Agent):
    """Tester role. Its validation output is never model-derived: it genuinely
    executes pytest against an allowlisted target directory, and the resulting
    pass/fail is the real evidence used for release-readiness gating. It may
    additionally write a clearly-labeled PROPOSED test-strategy note (model-
    assisted or a deterministic fallback) — proposed tests are never conflated
    with the executed test_report."""

    role = "tester"

    def __init__(self, model: Optional[ModelAdapter] = None):
        self.model = model or MockModelAdapter()

    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        target = task.context.get("test_target", "unit")

        proposal = _model_assist(
            self.model, self.role,
            f"Propose edge-case tests (do not execute) for: {requirement.original_text}",
            context.get("timeout_seconds", 30),
        ) or "(deterministic fallback) cover unit/integration paths already present in tests/."
        proposal_ref = _write(
            context["artifacts_dir"], f"proposed_tests_{task.id}.md",
            f"# Proposed tests (PROPOSED — not executed) — {task.id}\n\n{proposal}",
        )

        result = run_tests(target, timeout_seconds=context.get("timeout_seconds", 60))
        report = {
            "status": "EXECUTED",
            "target": target,
            "target_dirs": result.target_dirs,
            "passed": result.passed,
            "return_code": result.return_code,
            "duration_seconds": result.duration_seconds,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }
        report_ref = _write(context["artifacts_dir"], f"test_report_{task.id}.json", json.dumps(report, indent=2))
        return AgentResult(
            success=result.passed,
            output_refs=[report_ref, proposal_ref],
            error_summary=None if result.passed else f"pytest failed (rc={result.return_code}) for target={target}",
            details=report,
        )


class ImpactAnalysisAgent(Agent):
    def execute(self, task, context: dict) -> AgentResult:
        lines = [
            f"# Impact analysis — {context['run_id']}",
            "",
            "Modules touched by adding/confirming analytics on existing short URLs:",
            "- `src/agentic_engineer/url_shortener/service.py` (record_click, get_analytics)",
            "- `src/agentic_engineer/url_shortener/repository.py` (click_events table)",
            "- `src/agentic_engineer/api/app.py` (GET /api/urls/{code}/analytics)",
            "",
            "Redirect path (`GET /r/{code}`) is unaffected by this change; analytics writes",
            "are isolated and failures there must not raise past `record_click`.",
        ]
        ref = _write(context["artifacts_dir"], "impact_analysis.md", "\n".join(lines))
        return AgentResult(success=True, output_refs=[ref])


class ClarificationAgent(Agent):
    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        decision = task.approval_decision or {}
        payload = {
            "ambiguities": requirement.ambiguities,
            "resolution_notes": decision.get("resolution_notes", ""),
            "decided_by": decision.get("approver"),
            "decision": decision.get("decision"),
        }
        ref = _write(context["artifacts_dir"], "clarification.json", json.dumps(payload, indent=2))
        return AgentResult(success=True, output_refs=[ref], details=payload)


class DocumentAgent(Agent):
    """Documentation role: architecture, setup, API, assumptions, risks, and
    limitations. Optionally model-assisted for prose; deterministic fallback
    always included."""

    role = "documentation"

    def __init__(self, model: Optional[ModelAdapter] = None):
        self.model = model or MockModelAdapter()

    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        lines = [
            f"# Generated documentation — {context['run_id']}",
            "",
            "## Setup",
            "See README.md for installation and run instructions.",
            "",
            "## API",
            "See docs/api.md for the endpoint reference.",
            "",
            "## Limitations",
            "- Prototype uses SQLite and local-file run state (not multi-region).",
            "- Mock agents are deterministic; no live LLM call is required to run the demo.",
        ]
        if requirement.mode == "ambiguous":
            lines += ["", "## Clarified assumptions", *[f"- {a}" for a in requirement.assumptions]]
        assist = _model_assist(
            self.model, self.role,
            f"Draft a short risks-and-trade-offs note for: {requirement.original_text}",
            context.get("timeout_seconds", 30),
        )
        if assist:
            lines += ["", "## AI-assisted notes", assist]
        ref = _write(context["artifacts_dir"], "generated_docs.md", "\n".join(lines))
        return AgentResult(success=True, output_refs=[ref])


class ReleaseReadinessAgent(Agent):
    def execute(self, task, context: dict) -> AgentResult:
        results = context.get("results", {})
        blockers = []
        for dep_id in task.depends_on:
            dep_result = results.get(dep_id)
            if dep_result is None or not dep_result.success:
                blockers.append(dep_id)
        go = len(blockers) == 0
        report = {
            "go_no_go": "GO" if go else "NO_GO",
            "scope": "release_candidate_only",
            "deployment_authorized": False,
            "evaluated_gates": task.depends_on,
            "blocking_gates": blockers,
        }
        ref = _write(context["artifacts_dir"], "readiness.json", json.dumps(report, indent=2))
        return AgentResult(success=go, output_refs=[ref], details=report,
                            error_summary=None if go else f"blocked by: {blockers}")


class ReleaseApprovalAgent(Agent):
    """Records an approved release candidate only; it never deploys or publishes."""

    def execute(self, task, context: dict) -> AgentResult:
        decision = task.approval_decision or {}
        if decision.get("decision") != "APPROVED":
            return AgentResult(
                success=False,
                retryable=False,
                error_summary="release candidate has no recorded approval",
            )
        manifest = {
            "run_id": context["run_id"],
            "plan_id": context["plan_id"],
            "plan_version": context["plan_version"],
            "release_state": "APPROVED_CANDIDATE",
            "deployment_state": "NOT_DEPLOYED",
            "approver": decision.get("approver"),
            "approved_at": decision.get("decided_at"),
            "rationale": decision.get("rationale"),
            "required_readiness_task": task.depends_on[0] if task.depends_on else None,
        }
        ref = _write(
            context["artifacts_dir"], "release_manifest.json",
            json.dumps(manifest, indent=2),
        )
        return AgentResult(success=True, output_refs=[ref], details=manifest)


class OperationsHandoffAgent(Agent):
    """Produces an operations checklist and explicitly marks deployment as pending."""

    def execute(self, task, context: dict) -> AgentResult:
        content = "\n".join([
            f"# Operations handoff — {context['run_id']}",
            "",
            "Status: NOT DEPLOYED. No environment or hosting target is configured.",
            "",
            "## Before deployment",
            "- Select and approve a target environment and deployment method.",
            "- Configure HTTPS, API authentication/authorization, and rate limiting.",
            "- Decide analytics retention/privacy policy and implement the corresponding controls.",
            "- Configure durable database storage and tested backup/restore procedures.",
            "- Provide secret management, log retention, alert routing, and an on-call owner.",
            "",
            "## Health and monitoring",
            "- Probe `GET /health` after deployment; this endpoint currently reports process health only.",
            "- Monitor redirect/create error rates, latency, database availability, and click-write failures.",
            "- Confirm alerts and dashboards in the chosen hosting environment; none are configured by this prototype.",
            "",
            "## Recovery",
            "- Roll back the application to the previous approved release candidate.",
            "- Restore SQLite data only from a verified backup; no automated production rollback is implemented.",
            "- Record the incident, recovery decision, and validation evidence in the run audit trail.",
        ])
        ref = _write(context["artifacts_dir"], "operations_runbook.md", content)
        return AgentResult(success=True, output_refs=[ref], details={"deployment_state": "NOT_DEPLOYED"})


class SummarizeAgent(Agent):
    def execute(self, task, context: dict) -> AgentResult:
        requirement = context["requirement"]
        results = context.get("results", {})
        lines = [
            f"# Run summary — {context['run_id']}",
            "",
            f"Requirement: {requirement.original_text}",
            f"Mode: {requirement.mode}",
            "",
            "## Task outcomes",
        ]
        for tid, res in results.items():
            lines.append(f"- {tid}: {'SUCCEEDED' if res.success else 'FAILED'}")
        ref = _write(context["artifacts_dir"], "summary.md", "\n".join(lines))
        return AgentResult(success=True, output_refs=[ref])


def build_default_registry(model: Optional[ModelAdapter] = None):
    from .base import AgentRegistry

    registry = AgentRegistry()
    registry.register("intake", IntakeAgent())
    registry.register("understand", UnderstandAgent())
    registry.register("design", DesignAgent(model=model))
    registry.register("implement", ImplementAgent(model=model))
    registry.register("test", TestAgent(model=model))
    registry.register("impact_analysis", ImpactAnalysisAgent())
    registry.register("clarification", ClarificationAgent())
    registry.register("document", DocumentAgent(model=model))
    registry.register("release_readiness", ReleaseReadinessAgent())
    registry.register("release_approval", ReleaseApprovalAgent())
    registry.register("operations_handoff", OperationsHandoffAgent())
    registry.register("summarize", SummarizeAgent())
    return registry
