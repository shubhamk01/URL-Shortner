# Security, Compliance, and Change-Control Guardrails

## Human approval checkpoints
Tasks with `requires_approval=True` pause in `WAITING_FOR_APPROVAL` *before* the agent executes. Today this gates:
- Design tasks (API/data design decisions) in every scenario mode.
- The clarification gate in the ambiguous scenario (the human supplies the missing product/privacy decisions before any implementation proceeds).

Each decision is recorded as an `ApprovalRecord`: `task_id`, `approver`, `decision` (`APPROVED`/`REJECTED`), `rationale`, `resolution_notes`, `requested_at`, `decided_at`. Rejection cancels the task and blocks its descendants — the gated action never runs.

No destructive action (schema migration, deployment, publishing) is implemented in this prototype. Release readiness evaluates validation evidence; a separate human gate records release-candidate approval and the manifest remains `NOT_DEPLOYED`.

The runtime Copilot adapter passes an empty `available_tools` list to each SDK session and does not auto-approve tool requests. Copilot can return text suggestions, but receives no SDK built-in shell/filesystem tools through this adapter. Release approval records an approved candidate only; deployment remains unavailable until an environment-specific pipeline and its separate approvals are configured.

## Guardrails (policies/guardrails.py)
- **URL scheme allow-list**: only `http`/`https` destinations are accepted by the URL shortener (open-redirect/XSS mitigation).
- **Output-path sandboxing**: every artifact an agent writes is resolved against the run's `artifacts/` directory and rejected (`PolicyViolation`) if it would escape that root — no path traversal.
- **Command allow-list**: the validation subsystem only ever invokes `python -m pytest <allowlisted dirs>` as a subprocess with a timeout. No agent output is ever passed to a shell. There is no "run arbitrary command" capability anywhere in the system.
- **Secret redaction**: audit event details are passed through a redaction filter (`redact()`) before being written to `events.jsonl`, stripping obvious `key=`/`token=`/`password=`-shaped substrings.
- **Bounded retries/repairs**: every task has `max_attempts`; the engine creates at most one bounded repair task per failed task — no unbounded retry/repair loops.
- **Safe-stop**: `engine.request_safe_stop()` stops all *new* scheduling immediately; already-running tasks are allowed to finish (a prototype cannot safely force-kill a live subprocess — documented limitation, not claimed otherwise).
- **Rollback**: `engine.rollback_task()` only reverses a `FAILED` task's own recorded artifact writes; anything not reliably reversible is left for a human.

## Threat model notes for the prototype
- Requirement text and any agent/tool output are treated as **data**, never as trusted instructions — the rule-based requirement analyzer does not execute or interpret the text as commands, and no agent can expand its own permissions based on what it reads.
- Credentials (`AI_API_KEY`) are read from the environment only; they are never interpolated into prompts, file artifacts, or audit logs.
- SQLite access is fully parameterized; there is no string-built SQL anywhere in `url_shortener/repository.py`.
