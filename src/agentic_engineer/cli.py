"""Command-line interface for the agentic engineering system."""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from .config import get_settings
from .observability.audit import AuditLog
from .observability.metrics import compute_metrics
from .orchestration.pipeline import run_requirement
from .persistence.state_store import StateStore
from .reporting.summary import render_run_report


def _cmd_run(args: argparse.Namespace) -> int:
    if args.example:
        data = json.loads(Path(args.example).read_text(encoding="utf-8"))
        requirement_text = data["requirement"]
    elif args.requirement:
        requirement_text = args.requirement
    else:
        print("error: provide --requirement or --example", file=sys.stderr)
        return 2

    settings = get_settings()
    if args.auto_approve:
        settings = dataclasses.replace(settings, auto_approve=True)

    outcome = run_requirement(requirement_text, settings=settings)
    print(f"run_id={outcome.run_id} status={outcome.status}")
    print(f"inspect with: python -m agentic_engineer.cli inspect {outcome.run_id}")
    return 0 if outcome.status == "COMPLETED" else 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    settings = get_settings()
    state_store = StateStore(settings.runs_dir)
    audit_log = AuditLog(settings.runs_dir)
    print(render_run_report(args.run_id, state_store, audit_log))
    return 0


def _cmd_metrics(args: argparse.Namespace) -> int:
    settings = get_settings()
    audit_log = AuditLog(settings.runs_dir)
    metrics = compute_metrics(audit_log, run_id=args.run_id)
    print(json.dumps(metrics, indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("agentic_engineer.api.app:app", host=args.host, port=args.port, reload=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic_engineer", description="Agentic software engineering prototype")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run a requirement end to end")
    p_run.add_argument("--requirement", help="Requirement text")
    p_run.add_argument("--example", help="Path to an example scenario JSON file")
    p_run.add_argument("--auto-approve", action="store_true", help="Auto-approve all gates (demo convenience)")
    p_run.set_defaults(func=_cmd_run)

    p_inspect = sub.add_parser("inspect", help="Inspect a run's plan, tasks, and recent audit events")
    p_inspect.add_argument("run_id")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_metrics = sub.add_parser("metrics", help="Compute reliability metrics from audit events")
    p_metrics.add_argument("--run-id", default=None)
    p_metrics.set_defaults(func=_cmd_metrics)

    p_serve = sub.add_parser("serve", help="Run the URL shortener API with uvicorn")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
