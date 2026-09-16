from __future__ import annotations

from pydantic import BaseModel, Field


class ObservedElement(BaseModel):
    """Compact description of one visible interactive control."""

    index: int
    tag: str
    role: str | None = None
    name: str | None = None
    label: str | None = None
    text: str | None = None
    input_type: str | None = None
    checked: bool | None = None
    disabled: bool = False


class PageObservation(BaseModel):
    """Compact state sent to the discovery model instead of raw page HTML."""

    url: str
    title: str
    visible_text: str
    interactive_elements: list[ObservedElement] = Field(default_factory=list)
