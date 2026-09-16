from __future__ import annotations

from pydantic import BaseModel, model_validator

from src.artifact.models import ActionType, Target


class AgentDecision(BaseModel):
    """One structured decision returned by the discovery LLM."""

    action: ActionType | None = None
    target: Target | None = None
    value: str | None = None
    reason: str
    done: bool = False

    @model_validator(mode="after")
    def validate_decision(self) -> "AgentDecision":
        if self.done:
            return self

        if self.action is None:
            raise ValueError("A non-terminal decision requires an action.")

        if self.action in {
            ActionType.CLICK,
            ActionType.TYPE,
            ActionType.SELECT,
            ActionType.READ,
        } and self.target is None:
            raise ValueError(f"Action '{self.action.value}' requires a target.")

        if self.action in {
            ActionType.TYPE,
            ActionType.SELECT,
            ActionType.NAVIGATE,
        } and self.value is None:
            raise ValueError(f"Action '{self.action.value}' requires a value.")

        return self
