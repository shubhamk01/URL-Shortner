# Testing Approach

## Layers

| Layer | Location | What it covers |
|---|---|---|
| Unit | `tests/unit/` | Short-code generation, SQLite repository, URL-shortener service rules (scheme validation, collision handling, expiry, best-effort click recording). |
| Integration | `tests/integration/` | FastAPI endpoints via `TestClient`: create, redirect, metadata, analytics, invalid input, unknown code. |
| Orchestration unit | `tests/scenarios/test_orchestrator.py` | The workflow engine in isolation, using lightweight fake agents (no real subprocess pytest calls): dependencies, parallel execution, synchronization, retries/repair, approval rejection, safe-stop, blocked validation, audit/rollback/metrics, replanning, release approval rejection, and operations-handoff topology. |
| Scenario (end-to-end) | `tests/scenarios/test_scenarios.py` | Runs the real pipeline (real agents, real pytest-based validation) for all three scenarios; verifies release candidate manifest and explicit `NOT_DEPLOYED` operations handoff. |
| CI | `.github/workflows/ci.yml` | Pull request/push quality gate on Python 3.11/3.12: pytest, `pip-audit --skip-editable` third-party dependency scan, wheel build, and uploaded test/package artifacts. The local editable project itself is excluded from PyPI advisory lookup. Uses `AI_PROVIDER=mock`; it does not deploy. The setuptools floor is 83.0.0 to address `PYSEC-2026-3447`. |

## Running tests

```bash
# fast layers only
pytest tests/unit tests/integration -q

# orchestration engine (fast, mocked agents)
pytest tests/scenarios/test_orchestrator.py -q

# full end-to-end scenarios (slower: spawns real pytest subprocesses as validation evidence)
pytest tests/scenarios/test_scenarios.py -q

# everything
pytest -q
```

The full suite (including the 3 end-to-end scenarios) takes roughly 50-90 seconds locally because scenario tests genuinely re-run the project's own pytest suite as task evidence. CI runs the suite on Python 3.11 and 3.12, audits installed dependencies with `pip-audit`, and builds a wheel; Copilot live tests remain opt-in and are not part of CI.

## What is deterministic vs. real
- Requirement analysis, design, implementation notes, impact analysis, clarification, documentation, release-readiness, and summary are produced by **deterministic mock agents** — no network calls, no nondeterminism, safe to assert on exact strings.
- The **test** task type is the one agent that is *not* mocked: it genuinely invokes `python -m pytest <allowlisted dir>` and the resulting pass/fail is real validation evidence, not a fabricated status.

## Known gaps
- Coverage is concentrated on behavior that is explicitly required by the assignment (dependency/parallel/sync/retry/approval/safe-stop/replanning/validation-gating/audit/metrics). It is not an exhaustive property-based test suite.
- The CI dependency audit and package build are workflow jobs rather than deterministic unit tests; the live Copilot smoke test requires authentication and remains opt-in.
