"""Task decomposition: turns a normalized requirement into a dependency-ordered task graph.

Three scenario modes are supported explicitly (greenfield, brownfield, ambiguous),
matching the required demonstration scenarios. Each plan intentionally contains
independent branches (parallelizable) that converge on a synchronization task
(`release_readiness`), and gates high-impact design decisions behind human approval.
"""
from __future__ import annotations

import uuid
from typing import Optional

from ..requirements.analyzer import NormalizedRequirement
from .models import PlanVersion, Task


def _new_plan_id() -> str:
    return f"plan-{uuid.uuid4().hex[:8]}"


class Planner:
    def create_plan(
        self,
        run_id: str,
        requirement: NormalizedRequirement,
        version: int = 1,
        parent_plan_id: Optional[str] = None,
        rationale: str = "initial plan",
    ) -> PlanVersion:
        if requirement.mode == "brownfield":
            tasks = self._brownfield_tasks(run_id, requirement, version)
        elif requirement.mode == "ambiguous":
            tasks = self._ambiguous_tasks(run_id, requirement, version)
        else:
            tasks = self._greenfield_tasks(run_id, requirement, version)
        return PlanVersion(
            plan_id=_new_plan_id(),
            run_id=run_id,
            version=version,
            tasks={t.id: t for t in tasks},
            parent_plan_id=parent_plan_id,
            rationale=rationale,
        )

    # -- scenario-specific graphs -------------------------------------------------

    def _greenfield_tasks(self, run_id: str, req: NormalizedRequirement, version: int) -> list[Task]:
        return [
            Task(id="intake", run_id=run_id, task_type="intake",
                 objective="Record the requirement and create a run.",
                 expected_artifacts=["requirement.json"], plan_version=version),
            Task(id="understand", run_id=run_id, task_type="understand", depends_on=["intake"],
                 objective="Normalize the requirement and list acceptance criteria.",
                 expected_artifacts=["normalized_requirement.json"], plan_version=version),
            Task(id="design", run_id=run_id, task_type="design", depends_on=["understand"],
                 objective="Produce API/data design for the URL shortener.",
                 expected_artifacts=["design.md"], risk_level="medium", requires_approval=True,
                 plan_version=version),
            Task(id="implement", run_id=run_id, task_type="implement", depends_on=["design"],
                 objective="Propose implementation changes for creation, redirects, and analytics.",
                 expected_artifacts=["implementation_notes.md"], plan_version=version),
            Task(id="test_unit", run_id=run_id, task_type="test", depends_on=["implement"],
                 objective="Run unit tests for the URL shortener core.",
                 acceptance_criteria=["All unit tests pass."], plan_version=version,
                 context={"test_target": "unit"}),
            Task(id="test_integration", run_id=run_id, task_type="test", depends_on=["implement"],
                 objective="Run API integration tests.",
                 acceptance_criteria=["All integration tests pass."], plan_version=version,
                 context={"test_target": "integration"}),
            Task(id="document", run_id=run_id, task_type="document", depends_on=["implement"],
                 objective="Generate setup, API, and limitations documentation.",
                 expected_artifacts=["generated_docs.md"], plan_version=version),
            Task(id="release_readiness", run_id=run_id, task_type="release_readiness",
                 depends_on=["test_unit", "test_integration", "document"],
                 objective="Evaluate gates and produce a go/no-go readiness report.",
                 expected_artifacts=["readiness.json"], plan_version=version),
            Task(id="release_approval", run_id=run_id, task_type="release_approval",
                 depends_on=["release_readiness"],
                 objective="Request human approval for the release candidate; do not deploy.",
                 expected_artifacts=["release_manifest.json"], risk_level="high",
                 requires_approval=True, plan_version=version),
            Task(id="operations_handoff", run_id=run_id, task_type="operations_handoff",
                 depends_on=["release_approval"],
                 objective="Prepare an operations handoff and list unconfigured production controls.",
                 expected_artifacts=["operations_runbook.md"], plan_version=version),
            Task(id="summarize", run_id=run_id, task_type="summarize", depends_on=["operations_handoff"],
                 objective="Produce the final run summary.",
                 expected_artifacts=["summary.md"], plan_version=version),
        ]

    def _brownfield_tasks(self, run_id: str, req: NormalizedRequirement, version: int) -> list[Task]:
        return [
            Task(id="intake", run_id=run_id, task_type="intake",
                 objective="Record the requirement and create a run.",
                 expected_artifacts=["requirement.json"], plan_version=version),
            Task(id="understand", run_id=run_id, task_type="understand", depends_on=["intake"],
                 objective="Normalize the requirement and list acceptance criteria.",
                 expected_artifacts=["normalized_requirement.json"], plan_version=version),
            Task(id="inspect_baseline", run_id=run_id, task_type="test", depends_on=["understand"],
                 objective="Run the existing test suite to establish a passing baseline.",
                 acceptance_criteria=["Existing tests pass before any change."], plan_version=version,
                 context={"test_target": "regression"}),
            Task(id="impact_analysis", run_id=run_id, task_type="impact_analysis",
                 depends_on=["inspect_baseline"],
                 objective="Identify modules/data flows impacted by adding analytics.",
                 expected_artifacts=["impact_analysis.md"], plan_version=version),
            Task(id="design", run_id=run_id, task_type="design", depends_on=["impact_analysis"],
                 objective="Produce a backward-compatible change plan for analytics.",
                 expected_artifacts=["design.md"], risk_level="medium", requires_approval=True,
                 plan_version=version),
            Task(id="implement", run_id=run_id, task_type="implement", depends_on=["design"],
                 objective="Propose analytics changes without changing the redirect contract.",
                 expected_artifacts=["implementation_notes.md", "diff.md"], plan_version=version),
            Task(id="regression_tests", run_id=run_id, task_type="test", depends_on=["implement"],
                 objective="Re-run the full existing suite to confirm no regressions.",
                 acceptance_criteria=["No existing test regresses."], plan_version=version,
                 context={"test_target": "regression"}),
            Task(id="new_analytics_tests", run_id=run_id, task_type="test", depends_on=["implement"],
                 objective="Run new analytics-specific tests.",
                 acceptance_criteria=["New analytics tests pass."], plan_version=version,
                 context={"test_target": "unit"}),
            Task(id="document_diff", run_id=run_id, task_type="document", depends_on=["implement"],
                 objective="Document the change, affected modules, and decision lineage.",
                 expected_artifacts=["generated_docs.md"], plan_version=version),
            Task(id="release_readiness", run_id=run_id, task_type="release_readiness",
                 depends_on=["regression_tests", "new_analytics_tests", "document_diff"],
                 objective="Evaluate gates and produce a go/no-go readiness report.",
                 expected_artifacts=["readiness.json"], plan_version=version),
            Task(id="release_approval", run_id=run_id, task_type="release_approval",
                 depends_on=["release_readiness"],
                 objective="Request human approval for the release candidate; do not deploy.",
                 expected_artifacts=["release_manifest.json"], risk_level="high",
                 requires_approval=True, plan_version=version),
            Task(id="operations_handoff", run_id=run_id, task_type="operations_handoff",
                 depends_on=["release_approval"],
                 objective="Prepare an operations handoff and list unconfigured production controls.",
                 expected_artifacts=["operations_runbook.md"], plan_version=version),
            Task(id="summarize", run_id=run_id, task_type="summarize", depends_on=["operations_handoff"],
                 objective="Produce the final run summary.",
                 expected_artifacts=["summary.md"], plan_version=version),
        ]

    def _ambiguous_tasks(self, run_id: str, req: NormalizedRequirement, version: int) -> list[Task]:
        return [
            Task(id="intake", run_id=run_id, task_type="intake",
                 objective="Record the requirement and create a run.",
                 expected_artifacts=["requirement.json"], plan_version=version),
            Task(id="understand", run_id=run_id, task_type="understand", depends_on=["intake"],
                 objective="Normalize the requirement and surface ambiguities.",
                 expected_artifacts=["normalized_requirement.json"], risk_level="high",
                 plan_version=version),
            Task(id="clarification_gate", run_id=run_id, task_type="clarification",
                 depends_on=["understand"],
                 objective="Ask the human to resolve open ambiguities before committing to behavior.",
                 expected_artifacts=["clarification.json"], risk_level="high", requires_approval=True,
                 plan_version=version),
            Task(id="design", run_id=run_id, task_type="design", depends_on=["clarification_gate"],
                 objective="Produce a design based on clarified or explicit low-risk assumptions.",
                 expected_artifacts=["design.md"], risk_level="medium", requires_approval=True,
                 plan_version=version),
            Task(id="implement", run_id=run_id, task_type="implement", depends_on=["design"],
                 objective="Propose changes for the clarified safety and usage-tracking behavior.",
                 expected_artifacts=["implementation_notes.md"], plan_version=version),
            Task(id="test_unit", run_id=run_id, task_type="test", depends_on=["implement"],
                 objective="Run unit tests covering the clarified behavior.",
                 acceptance_criteria=["All unit tests pass."], plan_version=version,
                 context={"test_target": "unit"}),
            Task(id="document", run_id=run_id, task_type="document", depends_on=["implement"],
                 objective="Document the clarified decisions and remaining risks.",
                 expected_artifacts=["generated_docs.md"], plan_version=version),
            Task(id="release_readiness", run_id=run_id, task_type="release_readiness",
                 depends_on=["test_unit", "document"],
                 objective="Evaluate gates and produce a go/no-go readiness report.",
                 expected_artifacts=["readiness.json"], plan_version=version),
            Task(id="release_approval", run_id=run_id, task_type="release_approval",
                 depends_on=["release_readiness"],
                 objective="Request human approval for the release candidate; do not deploy.",
                 expected_artifacts=["release_manifest.json"], risk_level="high",
                 requires_approval=True, plan_version=version),
            Task(id="operations_handoff", run_id=run_id, task_type="operations_handoff",
                 depends_on=["release_approval"],
                 objective="Prepare an operations handoff and list unconfigured production controls.",
                 expected_artifacts=["operations_runbook.md"], plan_version=version),
            Task(id="summarize", run_id=run_id, task_type="summarize", depends_on=["operations_handoff"],
                 objective="Produce the final run summary.",
                 expected_artifacts=["summary.md"], plan_version=version),
        ]

    # -- replanning ----------------------------------------------------------

    def replan_after_clarification(
        self, old_plan: PlanVersion, requirement: NormalizedRequirement, resolution_notes: str
    ) -> PlanVersion:
        """Creates a new plan version: preserves already-succeeded upstream tasks
        (intake/understand/clarification_gate) and regenerates downstream tasks
        with acceptance criteria updated from the clarification answers.
        """
        from .models import Task as _Task
        from .models import TaskState

        new_version = old_plan.version + 1
        preserved: dict[str, Task] = {
            tid: t for tid, t in old_plan.tasks.items() if t.state == TaskState.SUCCEEDED
        }
        fresh = self._ambiguous_tasks(old_plan.run_id, requirement, new_version)
        tasks: dict[str, Task] = {}
        for t in fresh:
            if t.id in preserved:
                tasks[t.id] = preserved[t.id]
                continue
            if t.id == "design":
                t.acceptance_criteria = list(t.acceptance_criteria) + [
                    f"Incorporates clarification answers: {resolution_notes}"
                ]
            t.parent_task_id = t.id  # lineage marker: same logical task, new plan version
            tasks[t.id] = t

        return PlanVersion(
            plan_id=_new_plan_id(),
            run_id=old_plan.run_id,
            version=new_version,
            tasks=tasks,
            parent_plan_id=old_plan.plan_id,
            rationale=f"Replanned after clarification: {resolution_notes}",
        )

    def create_repair_task(self, failed_task: Task, attempt_suffix: int) -> Task:
        """Creates a bounded repair task that takes over the failed task's role."""
        repair = Task(
            id=f"{failed_task.id}-repair-{attempt_suffix}",
            run_id=failed_task.run_id,
            task_type=failed_task.task_type,
            objective=f"Repair: {failed_task.objective}",
            depends_on=list(failed_task.depends_on),
            expected_artifacts=list(failed_task.expected_artifacts),
            acceptance_criteria=list(failed_task.acceptance_criteria),
            risk_level=failed_task.risk_level,
            requires_approval=failed_task.requires_approval,
            retryable=False,
            max_attempts=1,
            parent_task_id=failed_task.id,
            plan_version=failed_task.plan_version,
            context=dict(failed_task.context),
        )
        return repair
