# AGENTS.md

Instructions for AI coding agents (GitHub Copilot, etc.) working **on** this
repository's source code. This is distinct from [SKILLS.md](SKILLS.md), which
documents the agent roles that the *application itself* runs at runtime
(Planner/Developer/Tester/Documentation).

## Project in one paragraph

A prototype agentic software-engineering orchestration system. A requirement
goes in; a dependency-ordered task graph comes out and is executed by role
agents (Copilot SDK by default, deterministic mock available for tests/offline
runs) with human approval gates, bounded retries/repair, real pytest
validation, an audit trail, and reliability metrics. The demo application is a
URL shortener. See [DOCUMENTATION.md](DOCUMENTATION.md) for the full doc index.

## Setup

```bash
py -m venv .venv          # on this machine, the plain `python` alias is broken; use `py`
.venv\Scripts\pip install -e ".[dev]"      # Windows
# .venv/bin/pip install -e ".[dev]"        # macOS/Linux
```

## Build / run / test commands

```bash
# full test suite (~30-70s; scenario tests spawn real pytest subprocesses as validation evidence)
.venv\Scripts\python.exe -m pytest -q

# fast layers only
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q
.venv\Scripts\python.exe -m pytest tests/scenarios/test_orchestrator.py -q

# run the URL shortener API
.venv\Scripts\python.exe -m agentic_engineer.cli serve

# run a demonstration scenario
.venv\Scripts\python.exe -m agentic_engineer.cli run --example examples/greenfield.json --auto-approve
.venv\Scripts\python.exe -m agentic_engineer.cli inspect <run_id>
.venv\Scripts\python.exe -m agentic_engineer.cli metrics
```

There is no separate lint/format step configured; keep changes consistent with
the existing style (type hints, dataclasses, narrow interfaces).

## Directory map

```
src/agentic_engineer/
  api/, url_shortener/   real FastAPI + SQLite demo app (independent of orchestration)
  requirements/          rule-based requirement analyzer
  planning/              task graph model + planner (3 scenario modes, replanning, repair)
  orchestration/         workflow engine (scheduling/retries/approval/safe-stop) + pipeline wiring
  agents/                Agent protocol, registry, role agents (mock_agents.py)
  model/                 ModelAdapter interface; Copilot SDK (default) + Mock adapter
  approvals/, policies/, validation/, persistence/, observability/, reporting/
  cli.py                 run / inspect / metrics / serve subcommands
docs/                    architecture, api, security, testing, scenarios, trade-offs
examples/                greenfield / brownfield / ambiguous requirement JSON
tests/                   unit, integration, scenarios (orchestrator unit + end-to-end)
```

## Conventions and hard rules

- **Agents never mutate the orchestrator's own source tree.** Implementation/
  Design/Documentation agents write descriptive artifacts under a run's
  sandboxed `artifacts/` directory; only the Tester role executes real code
  (pytest, via an allow-listed directory, never an arbitrary command).
- **Only the workflow engine changes task state.** See
  `planning/models.py`'s transition table — don't add ad hoc state mutation in
  agents.
- **Don't name an instance attribute the same as a method.** `WorkflowEngine`
  uses `self.run_record` (not `self.run`) precisely because it previously
  collided with the `run()` method and broke at runtime.
- **Model calls are always optional and must fail soft.** Any `ModelAdapter`
  call is wrapped so auth/timeout/unavailable/empty-response errors fall back
  to deterministic output — never let a model failure fail a task.
- **Every new behavior needs a test.** Put fast/deterministic engine tests in
  `tests/scenarios/test_orchestrator.py` (fake agents, no subprocess); only
  the three required end-to-end scenarios belong in
  `tests/scenarios/test_scenarios.py` (real agents, real pytest execution).
- Don't commit `.venv/`, `.data/`, `.runs*/`, or `.pytest_cache/` (already in
  `.gitignore`).
- Keep `docs/*.md` honest — update them in the same change if behavior or
  trade-offs shift; don't let them drift from the code.
