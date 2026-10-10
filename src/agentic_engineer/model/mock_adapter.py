"""Deterministic adapter: the default, used by every automated test. Requires
no credentials, makes no network calls, and is never mistaken for a real
model's output because its content is explicitly labeled as a mock."""
from __future__ import annotations

from .adapter import ModelResponse


class MockModelAdapter:
    model_name = "mock"

    def complete(self, prompt: str, *, role: str, timeout_seconds: float = 30.0) -> ModelResponse:
        content = f"[mock:{role}] deterministic stand-in response (no live model configured)."
        return ModelResponse(content=content, model=self.model_name, raw={"prompt_len": len(prompt)})
