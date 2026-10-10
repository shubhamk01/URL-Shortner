"""Security and change-control guardrails shared by agents and the engine.

These are intentionally simple and explicit: allowlists over cleverness.
"""
from __future__ import annotations

import re
from pathlib import Path

ALLOWED_URL_SCHEMES = {"http", "https"}

# Only these pytest target directories may be executed by the validation runner.
# Agents/tasks can never supply an arbitrary shell command.
ALLOWED_TEST_TARGETS = {
    "unit": ["tests/unit"],
    "integration": ["tests/integration"],
    "regression": ["tests/unit", "tests/integration"],
}

_SECRET_PATTERN = re.compile(r"(api[_-]?key|token|secret|password)\s*[:=]\s*\S+", re.IGNORECASE)


class PolicyViolation(Exception):
    pass


def validate_output_path(path: str, root: Path) -> Path:
    """Ensures a generated artifact path stays within the run's sandboxed output root."""
    root = root.resolve()
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PolicyViolation(f"path '{path}' escapes the allowed output root '{root}'") from exc
    return candidate


def validate_test_target(target: str) -> list[str]:
    if target not in ALLOWED_TEST_TARGETS:
        raise PolicyViolation(f"test target '{target}' is not in the allowlist {sorted(ALLOWED_TEST_TARGETS)}")
    return ALLOWED_TEST_TARGETS[target]


def redact(text: str) -> str:
    """Best-effort redaction of secret-looking substrings before they are logged."""
    return _SECRET_PATTERN.sub(lambda m: m.group(0).split(m.group(1))[0] + m.group(1) + "=<redacted>", text)
