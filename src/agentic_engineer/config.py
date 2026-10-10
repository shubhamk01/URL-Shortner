"""Centralized configuration loaded from environment variables with safe local defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", ".data/url_shortener.db"))
    allowed_url_schemes: tuple[str, ...] = field(
        default_factory=lambda: tuple(_list(os.getenv("ALLOWED_URL_SCHEMES"), ["http", "https"]))
    )
    short_code_length: int = field(default_factory=lambda: int(os.getenv("SHORT_CODE_LENGTH", "7")))
    short_code_max_collision_attempts: int = field(
        default_factory=lambda: int(os.getenv("SHORT_CODE_MAX_COLLISION_ATTEMPTS", "5"))
    )
    runs_dir: str = field(default_factory=lambda: os.getenv("RUNS_DIR", ".runs"))
    max_concurrency: int = field(default_factory=lambda: int(os.getenv("MAX_CONCURRENCY", "3")))
    max_task_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_TASK_ATTEMPTS", "3")))
    task_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("TASK_TIMEOUT_SECONDS", "60")))
    run_budget_seconds: int = field(default_factory=lambda: int(os.getenv("RUN_BUDGET_SECONDS", "900")))
    auto_approve: bool = field(default_factory=lambda: _bool(os.getenv("AUTO_APPROVE"), False))
    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "copilot"))
    ai_api_key: str = field(default_factory=lambda: os.getenv("AI_API_KEY", ""))
    # Model identifier passed to the GitHub Copilot SDK's create_session(model=...).
    copilot_model: str = field(default_factory=lambda: os.getenv("COPILOT_MODEL", "gpt-5"))
    model_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("MODEL_TIMEOUT_SECONDS", "30")))


def get_settings() -> Settings:
    """Re-reads the environment on every call so tests can monkeypatch os.environ freely."""
    return Settings()
