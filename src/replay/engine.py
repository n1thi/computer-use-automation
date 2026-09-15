from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.artifact.models import (
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    CheckpointType,
    InputParameter,
    ParameterType,
    RunResult,
    RunStatus,
    Step,
    Target,
)
from src.surface.base import Surface

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ReplayEngine:
    """Executes a saved capability deterministically with no LLM decisions."""

    def __init__(self, surface: Surface, evidence_dir: str | Path = "evidence/replay") -> None:
        self.surface = surface
        self.evidence_dir = Path(evidence_dir)

    @staticmethod
    def load_artifact(path: str | Path) -> CapabilityArtifact:
        return CapabilityArtifact.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def run(self, artifact: CapabilityArtifact, inputs: dict[str, Any]) -> RunResult:
        try:
            normalized_inputs = self._validate_inputs(artifact, inputs)
        except (TypeError, ValueError) as exc:
            return RunResult(
                status=RunStatus.FAILURE,
                capability_name=artifact.name,
                message=f"Invalid invocation inputs: {exc}",
            )

        try:
            self.surface.open(self._resolve_string(artifact.entry_url, normalized_inputs))

            for step in artifact.steps:
                resolved_step = self._resolve_step(step, normalized_inputs)

                try:
                    self._execute_step(resolved_step)
                except Exception as exc:
                    outcome = self._detect_business_outcome(artifact)
                    if outcome:
                        return outcome
                    evidence = self._capture_failure(artifact.name, resolved_step.id)
                    return RunResult(
                        status=RunStatus.FAILURE,
                        capability_name=artifact.name,
                        failed_step=resolved_step.id,
                        message=f"Step execution failed: {exc}",
                        evidence=evidence,
                    )

                outcome = self._detect_business_outcome(artifact)
                if outcome:
                    return outcome

                if resolved_step.checkpoint and not self._checkpoint_met(resolved_step.checkpoint):
                    outcome = self._detect_business_outcome(artifact)
                    if outcome:
                        return outcome
                    evidence = self._capture_failure(artifact.name, resolved_step.id)
                    return RunResult(
                        status=RunStatus.FAILURE,
                        capability_name=artifact.name,
                        failed_step=resolved_step.id,
                        message=(
                            f"Checkpoint failed after '{resolved_step.id}': "
                            f"{resolved_step.checkpoint.description or resolved_step.checkpoint.type.value}"
                        ),
                        evidence=evidence,
                    )

            if not self._checkpoint_met(artifact.success_checkpoint):
                outcome = self._detect_business_outcome(artifact)
                if outcome:
                    return outcome
                evidence = self._capture_failure(artifact.name, "final_checkpoint")
                return RunResult(
                    status=RunStatus.FAILURE,
                    capability_name=artifact.name,
                    failed_step="final_checkpoint",
                    message="Final success checkpoint was not satisfied.",
                    evidence=evidence,
                )

            return RunResult(
                status=RunStatus.SUCCESS,
                capability_name=artifact.name,
                outputs=self._success_outputs(artifact),
            )
        except Exception as exc:
            evidence = self._capture_failure(artifact.name, "run")
            return RunResult(
                status=RunStatus.FAILURE,
                capability_name=artifact.name,
                message=f"Replay failed: {exc}",
                evidence=evidence,
            )

    def _validate_inputs(self, artifact: CapabilityArtifact, supplied: dict[str, Any]) -> dict[str, Any]:
        definitions = {item.name: item for item in artifact.inputs}
        unknown = sorted(set(supplied) - set(definitions))
        if unknown:
            raise ValueError(f"Unknown input(s): {', '.join(unknown)}")

        normalized: dict[str, Any] = {}
        for definition in artifact.inputs:
            if definition.name not in supplied:
                if definition.required:
                    raise ValueError(f"Missing required input '{definition.name}'.")
                continue
            normalized[definition.name] = self._validate_input_value(definition, supplied[definition.name])
        return normalized

    def _validate_input_value(self, definition: InputParameter, value: Any) -> Any:
        if definition.type == ParameterType.STRING:
            if not isinstance(value, str):
                raise TypeError(f"'{definition.name}' must be a string.")
            return value

        if definition.type == ParameterType.INTEGER:
            if isinstance(value, bool):
                raise TypeError(f"'{definition.name}' must be an integer.")
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"'{definition.name}' must be an integer.") from exc

        if definition.type == ParameterType.NUMBER:
            if isinstance(value, bool):
                raise TypeError(f"'{definition.name}' must be a number.")
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"'{definition.name}' must be a number.") from exc

        if definition.type == ParameterType.BOOLEAN:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in {"true", "false"}:
                return value.lower() == "true"
            raise TypeError(f"'{definition.name}' must be a boolean.")

        if definition.type == ParameterType.ENUM:
            if not isinstance(value, str):
                raise TypeError(f"'{definition.name}' must be a string enum value.")
            allowed = definition.allowed_values or []
            canonical = {item.lower(): item for item in allowed}
            if value.lower() not in canonical:
                raise ValueError(f"'{definition.name}' must be one of: {', '.join(allowed)}.")
            return canonical[value.lower()]

        return value

    def _resolve_string(self, value: str | None, inputs: dict[str, Any]) -> str | None:
        if value is None:
            return None

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in inputs:
                raise ValueError(f"Missing value for placeholder '{name}'.")
            return str(inputs[name])

        return _PLACEHOLDER.sub(replace, value)

    def _resolve_target(self, target: Target | None, inputs: dict[str, Any]) -> Target | None:
        if target is None:
            return None
        update: dict[str, Any] = {}
        for field in ("role", "name", "label", "text", "css", "xpath", "description"):
            value = getattr(target, field)
            if isinstance(value, str):
                update[field] = self._resolve_string(value, inputs)
        if target.stable_attribute is not None:
            update["stable_attribute"] = {
                key: self._resolve_string(value, inputs)
                for key, value in target.stable_attribute.items()
            }
        return target.model_copy(update=update)

    def _resolve_checkpoint(self, checkpoint: Checkpoint | None, inputs: dict[str, Any]) -> Checkpoint | None:
        if checkpoint is None:
            return None
        return checkpoint.model_copy(update={
            "value": self._resolve_string(checkpoint.value, inputs),
            "target": self._resolve_target(checkpoint.target, inputs),
        })

    def _resolve_step(self, step: Step, inputs: dict[str, Any]) -> Step:
        action = step.action.model_copy(update={
            "value": self._resolve_string(step.action.value, inputs),
        })
        return step.model_copy(update={
            "action": action,
            "target": self._resolve_target(step.target, inputs),
            "checkpoint": self._resolve_checkpoint(step.checkpoint, inputs),
        })

    def _execute_step(self, step: Step) -> None:
        action = step.action
        target = step.target

        if action.type == ActionType.CLICK:
            assert target is not None
            self.surface.click(target, action.timeout_ms)
        elif action.type == ActionType.TYPE:
            assert target is not None
            if action.value is None:
                raise ValueError("type action requires a value.")
            self.surface.type(target, action.value, action.timeout_ms)
        elif action.type == ActionType.SELECT:
            assert target is not None
            if action.value is None:
                raise ValueError("select action requires a value.")
            self.surface.select(target, action.value, action.timeout_ms)
        elif action.type == ActionType.READ:
            assert target is not None
            self.surface.read(target, action.timeout_ms)
        elif action.type == ActionType.WAIT:
            self.surface.wait(action.timeout_ms)
        elif action.type == ActionType.NAVIGATE:
            if action.value is None:
                raise ValueError("navigate action requires a URL in action.value.")
            self.surface.open(action.value)
        else:
            raise ValueError(f"Unsupported action type: {action.type}")

    def _checkpoint_met(self, checkpoint: Checkpoint) -> bool:
        if checkpoint.type == CheckpointType.TEXT_PRESENT:
            assert checkpoint.value is not None
            return self.surface.is_visible(Target(text=checkpoint.value), timeout_ms=5000)
        if checkpoint.type == CheckpointType.ELEMENT_VISIBLE:
            assert checkpoint.target is not None
            return self.surface.is_visible(checkpoint.target, timeout_ms=5000)
        if checkpoint.type == CheckpointType.URL_CONTAINS:
            assert checkpoint.value is not None
            return checkpoint.value in self.surface.current_url
        return False

    def _detect_business_outcome(self, artifact: CapabilityArtifact) -> RunResult | None:
        for code in artifact.known_business_outcomes:
            if self.surface.is_visible(Target(text=f"OUTCOME: {code}"), timeout_ms=150):
                return RunResult(
                    status=RunStatus.BUSINESS_OUTCOME,
                    capability_name=artifact.name,
                    code=code,
                    message=f"Known business outcome detected: {code}",
                )
        return None

    def _capture_failure(self, capability_name: str, step_id: str) -> list[str]:
        try:
            path = self.evidence_dir / f"{capability_name}_{step_id}.png"
            return [self.surface.screenshot(path)]
        except Exception:
            return []

    def _success_outputs(self, artifact: CapabilityArtifact) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        checkpoint = artifact.success_checkpoint
        if (
            checkpoint.type == CheckpointType.TEXT_PRESENT
            and checkpoint.value
            and checkpoint.value.startswith("CHECKPOINT:")
        ):
            value = checkpoint.value.split(":", 1)[1].strip()
            for output in artifact.outputs:
                if output.name == "review_status":
                    outputs[output.name] = value
        return outputs
