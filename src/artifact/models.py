from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


class ActionType(str, Enum):
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    READ = "read"
    WAIT = "wait"
    NAVIGATE = "navigate"


class ParameterType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"


class CheckpointType(str, Enum):
    TEXT_PRESENT = "text_present"
    ELEMENT_VISIBLE = "element_visible"
    URL_CONTAINS = "url_contains"


class RunStatus(str, Enum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    RECOVERABLE_ERROR = "recoverable_error"
    FAILURE = "failure"
    ESCALATED = "escalated"


class InputParameter(BaseModel):
    name: str
    type: ParameterType
    description: str | None = None
    required: bool = True
    sensitive: bool = False
    allowed_values: list[str] | None = None

    @model_validator(mode="after")
    def validate_enum_values(self) -> "InputParameter":
        if self.type == ParameterType.ENUM and not self.allowed_values:
            raise ValueError("Enum input parameters require a non-empty allowed_values list.")
        if self.type != ParameterType.ENUM and self.allowed_values is not None:
            raise ValueError("allowed_values may only be set when type is 'enum'.")
        return self


class OutputParameter(BaseModel):
    name: str
    type: ParameterType
    description: str | None = None
    sensitive: bool = False


class Target(BaseModel):
    role: str | None = None
    name: str | None = None
    label: str | None = None
    text: str | None = None
    stable_attribute: dict[str, str] | None = None
    css: str | None = None
    xpath: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def require_locator(self) -> "Target":
        if not any([
            bool(self.role and self.role.strip()),
            bool(self.name and self.name.strip()),
            bool(self.label and self.label.strip()),
            bool(self.text and self.text.strip()),
            bool(self.stable_attribute),
            bool(self.css and self.css.strip()),
            bool(self.xpath and self.xpath.strip()),
        ]):
            raise ValueError("Target requires at least one locator field.")
        return self


class Action(BaseModel):
    type: ActionType
    value: str | None = None
    timeout_ms: int = Field(default=5000, gt=0)


class Checkpoint(BaseModel):
    type: CheckpointType
    value: str | None = None
    target: Target | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_checkpoint_shape(self) -> "Checkpoint":
        if self.type in {CheckpointType.TEXT_PRESENT, CheckpointType.URL_CONTAINS} and not self.value:
            raise ValueError(f"{self.type.value} checkpoint requires a value.")
        if self.type == CheckpointType.ELEMENT_VISIBLE and self.target is None:
            raise ValueError("element_visible checkpoint requires a target.")
        return self


class Step(BaseModel):
    id: str
    description: str | None = None
    action: Action
    target: Target | None = None
    checkpoint: Checkpoint | None = None

    @model_validator(mode="after")
    def require_target_for_ui_actions(self) -> "Step":
        if self.action.type in {
            ActionType.CLICK, ActionType.TYPE, ActionType.SELECT, ActionType.READ
        } and self.target is None:
            raise ValueError(f"Action '{self.action.type.value}' requires a target.")
        return self


class CapabilityArtifact(BaseModel):
    schema_version: str = "1.0"
    artifact_version: str
    name: str
    description: str
    target_application: str
    entry_url: str
    inputs: list[InputParameter]
    outputs: list[OutputParameter]
    steps: list[Step]
    success_checkpoint: Checkpoint
    known_business_outcomes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_names_and_ids(self) -> "CapabilityArtifact":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique.")
        input_names = [p.name for p in self.inputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError("Input parameter names must be unique.")
        output_names = [p.name for p in self.outputs]
        if len(output_names) != len(set(output_names)):
            raise ValueError("Output parameter names must be unique.")
        return self


class RunResult(BaseModel):
    status: RunStatus
    capability_name: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    code: str | None = None
    failed_step: str | None = None
    message: str | None = None
    evidence: list[str] = Field(default_factory=list)
