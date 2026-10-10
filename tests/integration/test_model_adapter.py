"""Model adapter tests.

The mock-adapter and resolve_adapter-fallback tests always run and require no
credentials. The live smoke test is opt-in (COPILOT_SDK_LIVE_TEST=1) because it
requires an installed, authenticated github-copilot-sdk runtime — it is
skipped by default so the rest of the suite stays fully offline.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from agentic_engineer.config import Settings, get_settings
from agentic_engineer.model import MockModelAdapter, resolve_adapter
from agentic_engineer.model.adapter import ModelError
from agentic_engineer.model.copilot_adapter import CopilotModelAdapter


def make_settings(ai_provider="mock", copilot_model="gpt-5"):
    return Settings(
        database_path=":memory:",
        allowed_url_schemes=("http", "https"),
        short_code_length=7,
        short_code_max_collision_attempts=5,
        runs_dir=".runs-test",
        max_concurrency=1,
        max_task_attempts=1,
        task_timeout_seconds=30,
        run_budget_seconds=60,
        auto_approve=True,
        ai_provider=ai_provider,
        ai_api_key="",
        copilot_model=copilot_model,
        model_timeout_seconds=5,
    )


def test_mock_adapter_is_deterministic_and_needs_no_credentials():
    adapter = MockModelAdapter()
    response = adapter.complete("implement a thing", role="developer")
    assert response.model == "mock"
    assert "[mock:developer]" in response.content


def test_resolve_adapter_defaults_to_copilot(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    settings = get_settings()
    assert settings.ai_provider == "copilot"
    adapter = resolve_adapter(settings)
    assert isinstance(adapter, CopilotModelAdapter)


def test_mock_can_be_selected_explicitly():
    adapter = resolve_adapter(make_settings(ai_provider="mock"))
    assert isinstance(adapter, MockModelAdapter)


def test_resolve_adapter_falls_back_to_mock_when_sdk_unavailable(monkeypatch):
    # Simulate the optional github-copilot-sdk package not being installed.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "agentic_engineer.model.copilot_adapter" or name.endswith("copilot_adapter"):
            raise ImportError("simulated: github-copilot-sdk not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    adapter = resolve_adapter(make_settings(ai_provider="copilot"))
    assert isinstance(adapter, MockModelAdapter)


def test_copilot_adapter_disables_all_sdk_tools(monkeypatch):
    import copilot

    captured = {}

    class FakeSession:
        async def send_and_wait(self, prompt, timeout):
            return SimpleNamespace(
                type="assistant.message",
                data=SimpleNamespace(content="safe text response"),
            )

        async def disconnect(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def start(self):
            return None

        async def create_session(self, **kwargs):
            captured["session_kwargs"] = kwargs
            return FakeSession()

        async def stop(self):
            return None

    monkeypatch.setattr(copilot, "CopilotClient", FakeClient)
    response = CopilotModelAdapter(model="gpt-5").complete(
        "Return a brief suggestion.", role="developer", timeout_seconds=2,
    )

    assert response.content == "safe text response"
    assert captured["session_kwargs"]["available_tools"] == []
    assert "on_permission_request" not in captured["session_kwargs"]


@pytest.mark.skipif(
    os.environ.get("COPILOT_SDK_LIVE_TEST") != "1",
    reason="opt-in live smoke test: set COPILOT_SDK_LIVE_TEST=1 with an authenticated "
    "github-copilot-sdk runtime to exercise a real model call",
)
def test_copilot_adapter_live_smoke():
    from agentic_engineer.model.copilot_adapter import CopilotModelAdapter

    adapter = CopilotModelAdapter(model="gpt-5")
    try:
        response = adapter.complete("Reply with the word OK.", role="smoke-test", timeout_seconds=30)
    except ModelError as exc:
        pytest.skip(f"live model call unavailable in this environment: {exc}")
    assert response.content
