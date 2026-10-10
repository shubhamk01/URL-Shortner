# SKILLS.md — Runtime Agent Roles

This catalogs the agent "skills" the orchestration engine dispatches at
runtime via `AgentRegistry` (task_type → agent), implemented in
`src/agentic_engineer/agents/mock_agents.py`. For how AI coding agents should
work *on* this repository's own source, see [AGENTS.md](AGENTS.md).

Every role uses the real Copilot SDK by default through the `ModelAdapter`
interface (`src/agentic_engineer/model/`). Set `AI_PROVIDER=mock` for
deterministic offline/testing runs. A model failure
(auth/timeout/unavailable/empty-response) is always caught and the
deterministic output is used regardless — a skill never fails a task just
because the model is unavailable.

## Primary (AI-assisted) roles

### Planner — `design`
- **Interprets** the normalized requirement (and any clarification answers)
  into an API/data design.
- **Produces**: `design.md` (API routes, data model, acceptance criteria,
  clarified decisions).
- **Model-assisted**: optionally appends an "AI-assisted review" section
  flagging remaining ambiguity/risk. Never authoritative on its own.
- **Permissions**: may call the model; may not execute code or claim a change
  was applied.

### Developer — `implement`
- **Proposes** code changes against the real `url_shortener`/`api` modules and
  (for brownfield) a diff summary.
- **Produces**: `implementation_notes.md`, and for brownfield also `diff.md`
  — both explicitly titled "PROPOSED, not applied".
- **Model-assisted**: optionally appends an "AI-proposed change" section.
- **Permissions**: may call the model; **never** writes outside the run's
  `artifacts/` sandbox and **never** claims code was applied — only the
  pre-existing, already-tested `url_shortener` source is the real artifact of
  record.

### Tester — `test`
- **The only role that genuinely executes code.** Runs
  `python -m pytest <allow-listed dir>` as a subprocess (`validation/runner.py`)
  against `tests/unit`, `tests/integration`, or both (regression).
- **Produces**: `test_report_<task_id>.json` (status `EXECUTED`: pass/fail,
  return code, duration, stdout/stderr tail) — the real validation evidence
  release-readiness gates on.
- **Also produces**: `proposed_tests_<task_id>.md` (status `PROPOSED` — model-
  assisted edge-case suggestions, or a deterministic fallback note). Proposed
  and executed results are never conflated.
- **Permissions**: the only role allowed to spawn a subprocess, and only
  against the allow-listed test-target directories in
  `policies/guardrails.py` — never an arbitrary command.

### Documentation — `document`
- **Produces**: `generated_docs.md` (setup/API pointers, limitations, and for
  the ambiguous scenario, the clarified assumptions).
- **Model-assisted**: optionally appends an "AI-assisted notes" section
  (short risks/trade-offs draft).
- **Permissions**: may call the model; read/write confined to `artifacts/`.

## Supporting (deterministic-only) skills

These are orchestration bookkeeping steps, not AI-assisted — they never call
a model, by design (keeps the "requirements" and "release" stages auditable
and reproducible independent of any model).

| Skill | Task type | Produces |
|---|---|---|
| Intake | `intake` | `requirement.json` — records the run's requirement verbatim |
| Understand | `understand` | `normalized_requirement.json` — acceptance criteria, assumptions, ambiguities, mode |
| Impact analysis | `impact_analysis` | `impact_analysis.md` — modules/data flows touched (brownfield) |
| Clarification | `clarification` | `clarification.json` — captures the human's answer to detected ambiguities, which then drives a replan |
| Release readiness | `release_readiness` | `readiness.json` — go/no-go, evaluated against its dependencies' actual success/failure |
| Summarize | `summarize` | `summary.md` — final run summary: requirement, mode, task outcomes |

## Adding a new skill

1. Implement `Agent.execute(self, task, context) -> AgentResult` in
   `agents/mock_agents.py` (or a new module).
2. Register it under a `task_type` string in `build_default_registry()`.
3. Reference that `task_type` from a `Task` in `planning/planner.py`'s
   scenario graph(s).
4. Keep output confined to `context["artifacts_dir"]`
   (`policies.guardrails.validate_output_path`) — never write elsewhere.
5. If the skill needs the model, accept an optional `model: ModelAdapter`
   constructor argument and wrap every call so failures degrade gracefully
   (see `_model_assist()` in `mock_agents.py`).
6. Add a test: a fast orchestrator-level test with a fake agent if you're
   testing scheduling behavior, or extend the relevant scenario test if
   you're testing the skill's real output.
