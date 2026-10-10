"""Model adapter interface.

This is the only module that other layers are allowed to depend on for
AI/model access — it keeps GitHub Copilot SDK specifics (auth, transport,
session lifecycle) out of business logic and workflow control (see
orchestration/, agents/). Concrete adapters: CopilotModelAdapter (default real
SDK) and MockModelAdapter (explicit offline/testing mode, no credentials needed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ModelError(Exception):
    """Base class for all model adapter errors."""


class ModelAuthenticationError(ModelError):
    """Raised when the configured credentials/session cannot authenticate."""


class ModelTimeoutError(ModelError):
    """Raised when a model call exceeds its configured timeout."""


class ModelUnavailableError(ModelError):
    """Raised when the configured model/provider/SDK cannot be reached at all."""


class ModelEmptyResponseError(ModelError):
    """Raised when the model call succeeds but returns no usable content."""


@dataclass
class ModelResponse:
    content: str
    model: str
    raw: dict = field(default_factory=dict)


class ModelAdapter(Protocol):
    """Narrow interface every agent depends on instead of an SDK client directly."""

    model_name: str

    def complete(self, prompt: str, *, role: str, timeout_seconds: float = 30.0) -> ModelResponse:
        """Returns a ModelResponse or raises one of the ModelError subclasses above."""
        ...
