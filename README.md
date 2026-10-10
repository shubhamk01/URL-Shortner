# Agentic Software Engineering System — Prototype

A runnable SDLC orchestration foundation that accepts a software requirement,
interprets it, decomposes it into a dependency-ordered task graph, coordinates
AI-assisted engineering proposals, runs automated validation, and creates an
approved release-candidate record plus an operations handoff. It is not a
production deployment system: generated code is not applied and no environment
is deployed to.

The demonstration application is a URL shortener (create, redirect, click
analytics). **The primary thing being evaluated here is the agentic orchestration
layer**, not the URL-shortening API by itself.

See [docs/architecture.md](docs/architecture.md) for the full design,
[docs/scenarios.md](docs/scenarios.md) for the three required demonstrations, and
[docs/tradeoffs-and-limitations.md](docs/tradeoffs-and-limitations.md) for an honest
account of what was simplified.

## Requirements

- Python 3.11+ (tested locally on 3.12)
- The `github-copilot-sdk` is installed with the normal project dependencies.
- Runtime Copilot calls require an authenticated Copilot CLI session or a
  supported GitHub token environment variable. Set `COPILOT_MODEL` to select
  the model; Copilot is the default provider. If runtime authentication is
  unavailable, role agents fall back to deterministic output.
- Set `AI_PROVIDER=mock` for explicitly offline, deterministic runs. The URL
  shortener and test suite do not require Copilot authentication.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\pip install -e ".[dev]"
# macOS/Linux
.venv/bin/pip install -e ".[dev]"

copy .env.example .env   # or: cp .env.example .env
```

Sign in with the Copilot CLI before running scenarios that should use live
Copilot. To force deterministic offline behavior, set `AI_PROVIDER=mock` in
`.env`.

## Run the URL shortener API

```bash
python -m agentic_engineer.cli serve
# then: curl -X POST http://127.0.0.1:8000/api/urls -H "Content-Type: application/json" -d "{\"original_url\": \"https://example.com\"}"
```

Endpoints are documented in [docs/api.md](docs/api.md).

## Run an agentic engineering scenario

```bash
# Greenfield
python -m agentic_engineer.cli run --example examples/greenfield.json --auto-approve

# Brownfield
python -m agentic_engineer.cli run --example examples/brownfield.json --auto-approve

# Ambiguous requirement (omit --auto-approve to answer the clarification prompt yourself)
python -m agentic_engineer.cli run --example examples/ambiguous.json

# Or with your own requirement text:
python -m agentic_engineer.cli run --requirement "Create a URL shortener with click analytics." --auto-approve
```

Each run prints a `run_id`. Inspect the generated plan, dependency graph, task
states, and recent audit trail with:

```bash
python -m agentic_engineer.cli inspect <run_id>
```

Compute reliability metrics (success rate, retry frequency, rollback frequency,
latency, MTTR) from the recorded audit events:

```bash
python -m agentic_engineer.cli metrics
```

All run state lives under `.runs/<run_id>/` (plan versions, `events.jsonl` audit
log, and generated `artifacts/`) so it can be inspected directly as files, without
re-running anything. See [docs/scenarios.md](docs/scenarios.md) for exactly what
evidence each of the three required scenarios produces.

## Testing

```bash
pytest -q                                    # everything (~1 min; spawns real pytest subprocesses for validation evidence)
pytest tests/unit tests/integration -q       # URL shortener only (fast)
pytest tests/scenarios/test_orchestrator.py -q  # orchestration engine only (fast, mocked agents)
```

See [docs/testing.md](docs/testing.md) for what each layer covers.

Pull requests and pushes to `main`/`master` run [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
on Python 3.11 and 3.12. CI runs pytest, audits installed dependencies with
`pip-audit`, builds a wheel, and uploads test/package evidence. It forces
`AI_PROVIDER=mock`, so CI never needs Copilot credentials.
To make this a merge gate, configure the repository ruleset/branch protection to
require both `Verify Python 3.11` and `Verify Python 3.12` checks; workflow YAML
alone cannot enforce that repository setting.

Each successful orchestrator run pauses for human release-candidate approval,
writes `release_manifest.json`, and produces `operations_runbook.md`. The
manifest explicitly says `NOT_DEPLOYED`; deployment requires a separately
approved, environment-specific delivery pipeline.

## Project layout

```
src/agentic_engineer/
  api/            FastAPI app for the URL shortener
  url_shortener/  domain models, codegen, SQLite repository, service layer
  requirements/   rule-based requirement analyzer (understand stage)
  planning/       task graph model + planner (3 scenario modes, replanning, repair)
  orchestration/  workflow engine (scheduling, retries, approval, safe-stop) + pipeline wiring
  agents/         agent protocol, registry, deterministic mock agents
  approvals/      human approval gate (pause/resume, audit trail)
  policies/       guardrails: URL/command allow-lists, path sandboxing, redaction
  validation/     real pytest-based test execution
  persistence/    run/plan JSON state store
  observability/  audit log (JSONL) + reliability metrics
  reporting/      human-readable run report rendering
  cli.py          command-line entry point
docs/             architecture, API, security, testing, scenarios, trade-offs
examples/         greenfield / brownfield / ambiguous requirement JSON
tests/            unit, integration, scenarios (orchestrator + end-to-end)
```

## Limitations

See [docs/tradeoffs-and-limitations.md](docs/tradeoffs-and-limitations.md) for
remaining gaps: agents propose but do not apply source patches; no CD/deployment,
production API authentication, durable distributed state, or configured
production monitoring is included.
