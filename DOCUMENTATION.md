# Documentation Index

Single entry point for every document in this repository.

## Start here

| Document | What it's for |
|---|---|
| [README.md](README.md) | Project overview, setup, how to run the URL shortener and the three demo scenarios, test commands. |
| [docs/application-guide.md](docs/application-guide.md) | End-to-end workflow, AI role/call map, Copilot credit-usage caveats, persisted evidence, and file-by-file source/test/docs inventory. |
| [AGENTS.md](AGENTS.md) | Instructions for AI coding agents (e.g. GitHub Copilot) working **on** this repo's source — build/test commands, directory map, hard rules. |
| [SKILLS.md](SKILLS.md) | Catalog of the runtime agent roles the orchestration engine dispatches (Planner/Developer/Tester/Documentation + bookkeeping skills) — what each produces and is/isn't permitted to do. |
| [.github/instructions/functionality.instructions.md](.github/instructions/functionality.instructions.md) | Product behavior, URL API contracts, scenario flows, and functional acceptance rules. |
| [.github/instructions/technicality.instructions.md](.github/instructions/technicality.instructions.md) | Source ownership map, system/AI-interference diagrams, and technical permission boundaries. |

## Design and behavior (`docs/`)

| Document | What it's for |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Full component table, control-flow diagram, task-graph/scheduling semantics, state persistence, agent boundaries and permissions table. |
| [docs/api.md](docs/api.md) | URL-shortener REST API reference (`POST /api/urls`, `GET /r/{code}`, metadata, analytics, health) and security notes. |
| [docs/security-and-guardrails.md](docs/security-and-guardrails.md) | Human approval checkpoints, guardrails (URL/command allow-lists, path sandboxing, redaction, bounded retries/safe-stop/rollback), threat-model notes. |
| [docs/testing.md](docs/testing.md) | Test layers (unit/integration/orchestrator/end-to-end scenario), how to run each, what's deterministic vs. real. |
| [docs/scenarios.md](docs/scenarios.md) | How to reproduce the three required demonstration scenarios (greenfield, brownfield, ambiguous) and what evidence each produces. |
| [docs/tradeoffs-and-limitations.md](docs/tradeoffs-and-limitations.md) | Honest account of what was simplified and why, including the tool-disabled Copilot integration and remaining production gaps. |

## Quick links by task

- **Run a scenario**: [README.md § Run an agentic engineering scenario](README.md#run-an-agentic-engineering-scenario), details in [docs/scenarios.md](docs/scenarios.md).
- **Understand a specific agent's behavior/permissions**: [SKILLS.md](SKILLS.md).
- **Understand scheduling/retry/approval/replanning semantics**: [docs/architecture.md § Task graph semantics](docs/architecture.md#task-graph-semantics).
- **Enable the real GitHub Copilot SDK model**: [README.md § Requirements](README.md#requirements) and [docs/tradeoffs-and-limitations.md](docs/tradeoffs-and-limitations.md).
- **Run the tests**: [docs/testing.md](docs/testing.md).
- **Contribute code as/with an AI agent**: [AGENTS.md](AGENTS.md).
