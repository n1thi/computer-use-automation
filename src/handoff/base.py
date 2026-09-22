from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from src.artifact.models import Step
from src.surface.base import Surface


class HandoffResult(BaseModel):
    resumed: bool
    action_completed_by_human: bool = True
    evidence: list[str] = Field(default_factory=list)


class HandoffHandler(Protocol):
    def handle(
        self,
        *,
        surface: Surface,
        capability_name: str,
        step: Step,
        reason: str,
    ) -> HandoffResult:
        ...
