# Demonstration Scenarios

All three scenarios use the same CLI entry point and the same workflow engine.
Run with `--auto-approve` for a non-interactive demo, or omit it to answer approval
prompts yourself on the CLI.

## Scenario A — Greenfield

```bash
python -m agentic_engineer.cli run --example examples/greenfield.json --auto-approve
```

Input: *"Create a URL shortener with click analytics."*

Expect: mode=`greenfield`, an 11-task plan (`intake → understand → design[approval] →
implement proposal → {test_unit, test_integration, document} → release_readiness →
release_approval[human] → operations_handoff → summarize`), parallel execution of
the post-implementation branches, a synchronization barrier at `release_readiness`,
and a release-candidate `GO` report backed by real pytest runs. Final approval
approves a candidate only; it does not deploy.

Evidence: `python -m agentic_engineer.cli inspect <run_id>` shows the task table and
recent audit events; `.runs/<run_id>/artifacts/` contains `design.md`,
`implementation_notes.md`, `test_report_test_unit.json`,
`test_report_test_integration.json`, `generated_docs.md`, `readiness.json`,
`release_manifest.json` (`NOT_DEPLOYED`), `operations_runbook.md`, and `summary.md`.

## Scenario B — Brownfield

```bash
python -m agentic_engineer.cli run --example examples/brownfield.json --auto-approve
```

Input: *"Add analytics to existing short URLs without breaking redirection."*

Expect: mode=`brownfield`, plan includes `inspect_baseline` (runs the *existing* test
suite first, as a real regression baseline) → `impact_analysis` → `design[approval]`
→ `implement proposal` → `{regression_tests, new_analytics_tests, document_diff}` →
`release_readiness` → `release_approval` → `operations_handoff` → `summarize`.

Evidence: `impact_analysis.md` lists the modules touched; `diff.md` explains why the
redirect contract is unaffected; `regression_tests`/`new_analytics_tests` are both
real pytest runs; `readiness.json` is `GO` only if required checks pass. A separate
human gate approves the release candidate; the operations handoff remains explicitly
not deployed.

## Scenario C — Ambiguous

```bash
python -m agentic_engineer.cli run --example examples/ambiguous.json
# (omit --auto-approve so you can supply clarification answers interactively)
```

Input: *"Make links safer and track usage."*

Expect: an 11-task plan; the requirement analyzer detects vague terms ("safer", "track usage") and
sets mode=`ambiguous`, `requires_clarification=True`. The plan pauses at
`clarification_gate` and asks concrete questions (e.g. "what does 'safer' mean?",
"what usage data is required and how long may it be retained?"). Your answer
(`resolution_notes`) is captured in `clarification.json` **and** triggers a
replan: a new plan version (v2) is created, linked to v1 via `parent_plan_id`,
carrying the already-succeeded `intake`/`understand`/`clarification_gate` tasks
forward unchanged and regenerating `design` (with your answer folded into its
acceptance criteria), then a human release approval and operations handoff. The
result remains a release candidate and is not deployed.

Evidence: `python -m agentic_engineer.cli inspect <run_id>` shows plan version 2;
`clarification.json` contains the ambiguities and your resolution notes;
`design.md` quotes your resolution text in its acceptance criteria.

To reproduce non-interactively (see `tests/scenarios/test_scenarios.py`), pass a
`decision_fn` to `orchestration.pipeline.run_requirement` instead of using the CLI.
