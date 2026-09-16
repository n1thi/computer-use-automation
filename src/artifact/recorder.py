from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from src.agent.models import AgentDecision
from src.artifact.models import (
    Action,
    CapabilityArtifact,
    Checkpoint,
    InputParameter,
    OutputParameter,
    Step,
    Target,
)


class ArtifactRecordingSpec(BaseModel):
    """Developer-declared capability contract; discovery supplies UI steps."""

    artifact_version: str = "1.0"
    name: str
    description: str
    target_application: str
    entry_url: str
    inputs: list[InputParameter]
    outputs: list[OutputParameter]
    success_checkpoint: Checkpoint
    known_business_outcomes: list[str] = Field(default_factory=list)


class ArtifactRecorder:
    """Convert a successful discovery trace into a reusable capability."""

    def record(
        self,
        *,
        decisions: list[AgentDecision],
        invocation_inputs: dict[str, str],
        spec: ArtifactRecordingSpec,
    ) -> CapabilityArtifact:
        self._validate_invocation_inputs(spec, invocation_inputs)

        steps: list[Step] = []

        for decision in decisions:
            if decision.done or decision.action is None:
                continue

            steps.append(
                Step(
                    id=f"step_{len(steps) + 1}",
                    description=self._parameterize_free_text(
                        decision.reason,
                        invocation_inputs,
                    ),
                    action=Action(
                        type=decision.action,
                        value=self._parameterize_exact(
                            decision.value,
                            invocation_inputs,
                        ),
                    ),
                    target=self._normalize_target(
                        decision.target,
                        invocation_inputs,
                    ),
                )
            )

        if not steps:
            raise ValueError(
                "Cannot record a capability from a discovery run with no actions."
            )

        return CapabilityArtifact(
            artifact_version=spec.artifact_version,
            name=spec.name,
            description=spec.description,
            target_application=spec.target_application,
            entry_url=spec.entry_url,
            inputs=spec.inputs,
            outputs=spec.outputs,
            steps=steps,
            success_checkpoint=spec.success_checkpoint,
            known_business_outcomes=spec.known_business_outcomes,
        )

    def save(
        self,
        artifact: CapabilityArtifact,
        path: str | Path,
    ) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            artifact.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return output

    def _validate_invocation_inputs(
        self,
        spec: ArtifactRecordingSpec,
        invocation_inputs: dict[str, str],
    ) -> None:
        declared = {item.name for item in spec.inputs}
        supplied = set(invocation_inputs)

        missing = [
            item.name
            for item in spec.inputs
            if item.required and item.name not in invocation_inputs
        ]
        if missing:
            raise ValueError(
                "Cannot record artifact: missing required invocation input(s): "
                + ", ".join(sorted(missing))
            )

        unknown = sorted(supplied - declared)
        if unknown:
            raise ValueError(
                "Cannot record artifact: invocation contains undeclared input(s): "
                + ", ".join(unknown)
            )

    def _parameterize_exact(
        self,
        value: str | None,
        invocation_inputs: dict[str, str],
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip().casefold()

        for name, raw in invocation_inputs.items():
            if normalized == str(raw).strip().casefold():
                return f"${{{name}}}"

        return value

    def _parameterize_free_text(
        self,
        value: str | None,
        invocation_inputs: dict[str, str],
    ) -> str | None:
        if value is None:
            return None

        result = value

        for name, raw in sorted(
            invocation_inputs.items(),
            key=lambda item: len(str(item[1])),
            reverse=True,
        ):
            raw_text = str(raw)
            if not raw_text:
                continue

            result = re.sub(
                re.escape(raw_text),
                f"${{{name}}}",
                result,
                flags=re.IGNORECASE,
            )

        return result

    def _normalize_target(
        self,
        target: Target | None,
        invocation_inputs: dict[str, str],
    ) -> Target | None:
        if target is None:
            return None

        if target.role and target.name:
            return Target(
                role=target.role,
                name=self._parameterize_exact(
                    target.name,
                    invocation_inputs,
                ),
            )

        if target.label:
            return Target(
                label=self._parameterize_exact(
                    target.label,
                    invocation_inputs,
                ),
            )

        if target.text:
            return Target(
                text=self._parameterize_exact(
                    target.text,
                    invocation_inputs,
                ),
            )

        if target.stable_attribute:
            return Target(
                stable_attribute={
                    key: self._parameterize_exact(value, invocation_inputs)
                    or value
                    for key, value in target.stable_attribute.items()
                }
            )

        if target.css:
            return Target(css=target.css)

        if target.xpath:
            return Target(xpath=target.xpath)

        if target.name:
            return Target(
                name=self._parameterize_exact(
                    target.name,
                    invocation_inputs,
                )
            )

        raise ValueError(
            "Discovery target could not be normalized into a replay locator."
        )
