from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.agent.llm_client import DecisionModel
from src.agent.models import AgentDecision
from src.artifact.models import ActionType, Checkpoint, CheckpointType, Target
from src.surface.base import Surface
from src.surface.models import ObservedElement, PageObservation


class DiscoveryStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    MAX_STEPS = "max_steps"


class DiscoveryRunResult(BaseModel):
    status: DiscoveryStatus
    goal: str
    steps_executed: int
    decisions: list[AgentDecision] = Field(default_factory=list)
    message: str | None = None
    log_path: str | None = None
    screenshot_path: str | None = None
    artifact_path: str | None = None


class DiscoveryRunner:
    def __init__(
        self,
        *,
        surface: Surface,
        decision_model: DecisionModel,
        success_checkpoint: Checkpoint | None = None,
        evidence_dir: str | Path = "evidence/discovery",
    ) -> None:
        self.surface = surface
        self.decision_model = decision_model
        self.success_checkpoint = success_checkpoint
        self.evidence_dir = Path(evidence_dir)

    def run(
        self,
        *,
        goal: str,
        inputs: dict[str, str],
        entry_url: str,
        max_steps: int = 10,
    ) -> DiscoveryRunResult:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        log_path = self.evidence_dir / f"discovery_{run_id}.jsonl"
        final_screenshot = self.evidence_dir / f"discovery_{run_id}_final.png"
        failure_screenshot = self.evidence_dir / f"discovery_{run_id}_failure.png"

        decisions: list[AgentDecision] = []
        history: list[dict[str, Any]] = []

        try:
            self.surface.open(entry_url)

            for step_number in range(1, max_steps + 1):
                if self.success_checkpoint and self._checkpoint_met(
                    self.success_checkpoint
                ):
                    screenshot = self.surface.screenshot(final_screenshot)
                    result = DiscoveryRunResult(
                        status=DiscoveryStatus.SUCCESS,
                        goal=goal,
                        steps_executed=len(decisions),
                        decisions=decisions,
                        message="Success checkpoint reached.",
                        log_path=str(log_path),
                        screenshot_path=screenshot,
                    )
                    self._write_event(
                        log_path,
                        {
                            "event": "run_complete",
                            "status": result.status.value,
                            "steps_executed": result.steps_executed,
                        },
                        inputs,
                    )
                    return result

                observation = self.surface.observe()

                decision = self.decision_model.decide(
                    goal=goal,
                    inputs=inputs,
                    observation=observation,
                    history=history,
                    success_condition=self._success_condition_text(),
                )

                self._write_event(
                    log_path,
                    {
                        "event": "decision",
                        "step": step_number,
                        "observation": observation.model_dump(mode="json"),
                        "decision": decision.model_dump(mode="json"),
                    },
                    inputs,
                )

                if decision.done:
                    if self.success_checkpoint is None or self._checkpoint_met(
                        self.success_checkpoint
                    ):
                        screenshot = self.surface.screenshot(final_screenshot)
                        decisions.append(decision)
                        return DiscoveryRunResult(
                            status=DiscoveryStatus.SUCCESS,
                            goal=goal,
                            steps_executed=len(decisions),
                            decisions=decisions,
                            message="Model declared the goal complete.",
                            log_path=str(log_path),
                            screenshot_path=screenshot,
                        )

                    screenshot = self.surface.screenshot(failure_screenshot)
                    return DiscoveryRunResult(
                        status=DiscoveryStatus.FAILURE,
                        goal=goal,
                        steps_executed=len(decisions),
                        decisions=decisions + [decision],
                        message=(
                            "Model declared completion before the configured "
                            "success checkpoint was satisfied."
                        ),
                        log_path=str(log_path),
                        screenshot_path=screenshot,
                    )

                if decision.target is not None and not self._target_is_observed(
                    decision.target,
                    observation,
                ):
                    screenshot = self.surface.screenshot(failure_screenshot)
                    return DiscoveryRunResult(
                        status=DiscoveryStatus.FAILURE,
                        goal=goal,
                        steps_executed=len(decisions),
                        decisions=decisions + [decision],
                        message=(
                            "Model selected a target that was not present in the "
                            "current page observation."
                        ),
                        log_path=str(log_path),
                        screenshot_path=screenshot,
                    )

                try:
                    read_value = self._execute(decision)
                except Exception as exc:
                    screenshot = self.surface.screenshot(failure_screenshot)
                    self._write_event(
                        log_path,
                        {
                            "event": "execution_error",
                            "step": step_number,
                            "error": str(exc),
                        },
                        inputs,
                    )
                    return DiscoveryRunResult(
                        status=DiscoveryStatus.FAILURE,
                        goal=goal,
                        steps_executed=len(decisions),
                        decisions=decisions + [decision],
                        message=f"Action execution failed: {exc}",
                        log_path=str(log_path),
                        screenshot_path=screenshot,
                    )

                decisions.append(decision)

                history_item = {
                    "step": step_number,
                    "action": decision.action.value if decision.action else None,
                    "target": (
                        decision.target.model_dump(mode="json")
                        if decision.target
                        else None
                    ),
                    "value": decision.value,
                    "reason": decision.reason,
                }
                if read_value is not None:
                    history_item["read_value"] = read_value

                history.append(history_item)

            screenshot = self.surface.screenshot(failure_screenshot)
            self._write_event(
                log_path,
                {
                    "event": "run_complete",
                    "status": DiscoveryStatus.MAX_STEPS.value,
                    "steps_executed": len(decisions),
                },
                inputs,
            )
            return DiscoveryRunResult(
                status=DiscoveryStatus.MAX_STEPS,
                goal=goal,
                steps_executed=len(decisions),
                decisions=decisions,
                message=f"Stopped after max_steps={max_steps}.",
                log_path=str(log_path),
                screenshot_path=screenshot,
            )

        except Exception as exc:
            screenshot: str | None = None
            try:
                screenshot = self.surface.screenshot(failure_screenshot)
            except Exception:
                pass

            self._write_event(
                log_path,
                {"event": "run_error", "error": str(exc)},
                inputs,
            )

            return DiscoveryRunResult(
                status=DiscoveryStatus.FAILURE,
                goal=goal,
                steps_executed=len(decisions),
                decisions=decisions,
                message=f"Discovery failed: {exc}",
                log_path=str(log_path),
                screenshot_path=screenshot,
            )

    def _execute(self, decision: AgentDecision) -> str | None:
        action = decision.action
        target = decision.target

        if action == ActionType.CLICK:
            assert target is not None
            self.surface.click(target)
            return None

        if action == ActionType.TYPE:
            assert target is not None
            assert decision.value is not None
            self.surface.type(target, decision.value)
            return None

        if action == ActionType.SELECT:
            assert target is not None
            assert decision.value is not None
            self.surface.select(target, decision.value)
            return None

        if action == ActionType.READ:
            assert target is not None
            return self.surface.read(target)

        if action == ActionType.WAIT:
            self.surface.wait(500)
            return None

        if action == ActionType.NAVIGATE:
            raise ValueError(
                "Model-driven navigation is blocked during discovery; "
                "the runner owns the entry URL."
            )

        raise ValueError(f"Unsupported discovery action: {action}")

    def _target_is_observed(
        self,
        target: Target,
        observation: PageObservation,
    ) -> bool:
        if target.css or target.xpath or target.stable_attribute:
            return False

        return any(
            self._element_matches_target(element, target)
            for element in observation.interactive_elements
        )

    @staticmethod
    def _element_matches_target(
        element: ObservedElement,
        target: Target,
    ) -> bool:
        def same(left: str | None, right: str | None) -> bool:
            if right is None:
                return True
            if left is None:
                return False
            return left.strip().casefold() == right.strip().casefold()

        return (
            same(element.role, target.role)
            and same(element.name, target.name)
            and same(element.label, target.label)
            and same(element.text, target.text)
        )

    def _checkpoint_met(self, checkpoint: Checkpoint) -> bool:
        if checkpoint.type == CheckpointType.TEXT_PRESENT:
            assert checkpoint.value is not None
            return self.surface.is_visible(
                Target(text=checkpoint.value),
                timeout_ms=250,
            )

        if checkpoint.type == CheckpointType.ELEMENT_VISIBLE:
            assert checkpoint.target is not None
            return self.surface.is_visible(
                checkpoint.target,
                timeout_ms=250,
            )

        if checkpoint.type == CheckpointType.URL_CONTAINS:
            assert checkpoint.value is not None
            return checkpoint.value in self.surface.current_url

        return False

    def _success_condition_text(self) -> str | None:
        if self.success_checkpoint is None:
            return None
        if self.success_checkpoint.type == CheckpointType.TEXT_PRESENT:
            return f"Visible text: {self.success_checkpoint.value}"
        if self.success_checkpoint.type == CheckpointType.URL_CONTAINS:
            return f"URL contains: {self.success_checkpoint.value}"
        if self.success_checkpoint.type == CheckpointType.ELEMENT_VISIBLE:
            if self.success_checkpoint.target:
                return (
                    "Element visible: "
                    f"{self.success_checkpoint.target.model_dump(mode='json')}"
                )
            return "Configured element checkpoint"
        return None

    def _write_event(
        self,
        path: Path,
        event: dict[str, Any],
        inputs: dict[str, str],
    ) -> None:
        safe_event = self._redact(event, inputs)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe_event, ensure_ascii=False) + "\n")

    def _redact(self, value: Any, inputs: dict[str, str]) -> Any:
        if isinstance(value, str):
            redacted = value
            for name, raw in sorted(
                inputs.items(),
                key=lambda item: len(str(item[1])),
                reverse=True,
            ):
                if raw:
                    redacted = redacted.replace(str(raw), f"${{{name}}}")
            return redacted

        if isinstance(value, list):
            return [self._redact(item, inputs) for item in value]

        if isinstance(value, dict):
            return {
                key: self._redact(item, inputs)
                for key, item in value.items()
            }

        return value
