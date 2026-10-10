"""Agent interface. Concrete agents only need to implement `execute`.

Keeping this interface model/provider-agnostic lets the workflow run entirely on
deterministic mock agents (see mock_agents.py) when no AI credentials are
configured, while leaving room to plug in a real LLM-backed agent later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AgentResult:
    success: bool
    output_refs: list[str] = field(default_factory=list)
    error_summary: str | None = None
    retryable: bool = True
    details: dict = field(default_factory=dict)


class Agent(Protocol):
    def execute(self, task, context: dict) -> AgentResult:
        ...


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def register(self, task_type: str, agent: Agent) -> None:
        self._agents[task_type] = agent

    def get(self, task_type: str) -> Agent:
        if task_type not in self._agents:
            raise KeyError(f"no agent registered for task_type '{task_type}'")
        return self._agents[task_type]
