"""Real GitHub Copilot SDK-backed model adapter.

Lazy-imports `copilot` (the `github-copilot-sdk` PyPI package, `pip install
github-copilot-sdk`) so the rest of the system runs without it installed.
Method names/signatures below were verified against the installed package
(CopilotClient, CopilotClient.create_session, and
CopilotSession.send_and_wait) rather than assumed — see docs/architecture.md.

Authentication is handled entirely by the SDK (a signed-in `copilot` CLI
session, `COPILOT_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN` env vars, or an
explicit `github_token` passed in here). Credentials are never logged or
embedded in a prompt.
"""
from __future__ import annotations

import asyncio

from .adapter import (
    ModelAuthenticationError,
    ModelEmptyResponseError,
    ModelError,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
)


class CopilotModelAdapter:
    def __init__(self, model: str, github_token: str | None = None):
        self.model_name = model
        self._github_token = github_token or None

    def complete(self, prompt: str, *, role: str, timeout_seconds: float = 30.0) -> ModelResponse:
        """Synchronous facade: each call spins up its own short-lived SDK client/session
        and event loop so callers (agents running in a thread pool) don't need asyncio."""
        try:
            return asyncio.run(self._complete_async(prompt, timeout_seconds))
        except ModelError:
            raise
        except TimeoutError as exc:
            raise ModelTimeoutError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - normalize every other SDK failure mode
            message = str(exc).lower()
            if "auth" in message or "token" in message or "unauthorized" in message or "401" in message:
                raise ModelAuthenticationError(str(exc)) from exc
            raise ModelUnavailableError(str(exc)) from exc

    async def _complete_async(self, prompt: str, timeout_seconds: float) -> ModelResponse:
        try:
            from copilot import CopilotClient
        except ImportError as exc:
            raise ModelUnavailableError(
                "github-copilot-sdk is not installed (pip install github-copilot-sdk)"
            ) from exc

        client = CopilotClient(github_token=self._github_token)
        await client.start()
        try:
            session = await client.create_session(
                model=self.model_name,
                available_tools=[],
            )
            try:
                event = await session.send_and_wait(prompt, timeout=timeout_seconds)
            finally:
                await session.disconnect()

            content = getattr(getattr(event, "data", None), "content", None) if event else None
            if not content:
                raise ModelEmptyResponseError("model returned no assistant content")
            return ModelResponse(
                content=content, model=self.model_name,
                raw={"event_type": getattr(event, "type", None)},
            )
        finally:
            await client.stop()
