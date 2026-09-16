from __future__ import annotations

import json
import os
from typing import Any, Protocol

from openai import OpenAI

from src.agent.models import AgentDecision
from src.surface.models import PageObservation


class DecisionModel(Protocol):
    def decide(
        self,
        *,
        goal: str,
        inputs: dict[str, str],
        observation: PageObservation,
        history: list[dict[str, Any]],
        success_condition: str | None = None,
    ) -> AgentDecision:
        ...


_SYSTEM_PROMPT = """
You are the discovery planner for a computer-use automation system.

You receive:
- a natural-language goal,
- invocation inputs,
- the current page observation,
- a short history of already executed actions,
- and optionally a success condition.

Choose exactly ONE next UI action.

Rules:
1. Use only controls present in `interactive_elements`.
2. Prefer semantic targeting with role + name. Reuse role/name exactly as observed.
3. Do not invent controls, selectors, XPath, or URLs.
4. For typing, use the exact requested input value.
5. For radio buttons or buttons, use `click`.
6. Use `select` only for a real select/combobox.
7. Do not navigate to a new URL. The runner owns initial navigation.
8. Set `done=true` only when the goal is already satisfied.
9. Keep `reason` to one short sentence about the immediate action.
10. Return only the structured AgentDecision requested by the schema.
""".strip()


class OpenAIDecisionModel:
    def __init__(
        self,
        model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        self.client = client or OpenAI()

    def decide(
        self,
        *,
        goal: str,
        inputs: dict[str, str],
        observation: PageObservation,
        history: list[dict[str, Any]],
        success_condition: str | None = None,
    ) -> AgentDecision:
        payload = {
            "goal": goal,
            "inputs": inputs,
            "success_condition": success_condition,
            "current_observation": observation.model_dump(mode="json"),
            "history": history[-8:],
        }

        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "developer", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, indent=2)},
            ],
            text_format=AgentDecision,
        )

        decision = response.output_parsed
        if decision is None:
            raise RuntimeError(
                "The model response did not contain a parsed AgentDecision."
            )

        return decision
