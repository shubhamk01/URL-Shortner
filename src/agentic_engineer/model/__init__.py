"""Model adapter package: GitHub Copilot SDK integration lives entirely behind
`ModelAdapter` (see adapter.py). Business logic and workflow control never
import `copilot` directly.
"""
from __future__ import annotations

from ..config import Settings
from .adapter import (
    ModelAdapter,
    ModelAuthenticationError,
    ModelEmptyResponseError,
    ModelError,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
)
from .mock_adapter import MockModelAdapter

__all__ = [
    "ModelAdapter",
    "ModelError",
    "ModelAuthenticationError",
    "ModelTimeoutError",
    "ModelUnavailableError",
    "ModelEmptyResponseError",
    "ModelResponse",
    "MockModelAdapter",
    "resolve_adapter",
]


def resolve_adapter(settings: Settings) -> ModelAdapter:
    """Copilot by default; mock remains an explicit option and a fail-soft fallback
    if the optional runtime cannot be imported. Model call failures are handled
    by agents so deterministic tasks/tests remain usable without authentication."""
    if settings.ai_provider.lower() == "mock":
        return MockModelAdapter()
    try:
        from .copilot_adapter import CopilotModelAdapter
    except ImportError:
        return MockModelAdapter()
    return CopilotModelAdapter(model=settings.copilot_model, github_token=settings.ai_api_key or None)
