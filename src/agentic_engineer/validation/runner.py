"""Runs real test validation via subprocess pytest invocations with bounded timeouts.

Only allowlisted target directories may be executed (see policies.guardrails),
so an agent can never smuggle an arbitrary shell command through this path.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..policies.guardrails import validate_test_target

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ValidationResult:
    passed: bool
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    target_dirs: list[str]


def run_tests(target: str, timeout_seconds: int = 60, cwd: Path | None = None) -> ValidationResult:
    dirs = validate_test_target(target)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *dirs, "-q"],
            cwd=str(cwd or REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return ValidationResult(
            passed=proc.returncode == 0,
            return_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_seconds=time.monotonic() - start,
            target_dirs=dirs,
        )
    except subprocess.TimeoutExpired as exc:
        return ValidationResult(
            passed=False,
            return_code=-1,
            stdout=exc.stdout or "",
            stderr=f"validation timed out after {timeout_seconds}s",
            duration_seconds=time.monotonic() - start,
            target_dirs=dirs,
        )
