from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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
from src.handoff.base import HandoffHandler
from src.safety.policy import (
    ExecutionPolicy,
    PolicyDisposition,
)
from src.surface.base import Surface

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ReplayEngine:
    """Execute a saved capability deterministically with no LLM decisions."""

    def __init__(
        self,
        surface: Surface,
        evidence_dir: str | Path = "evidence/replay",
        *,
        policy: ExecutionPolicy | None = None,
        handoff: HandoffHandler | None = None,
        checkpoint_retries: int = 1,
        checkpoint_retry_delay_ms: int = 300,
    ) -> None:
        if checkpoint_retries < 0:
            raise ValueError("checkpoint_retries must be >= 0.")
        if checkpoint_retry_delay_ms < 0:
            raise ValueError("checkpoint_retry_delay_ms must be >= 0.")

        self.surface = surface
        self.evidence_dir = Path(evidence_dir)
        self.policy = policy
        self.handoff = handoff
        self.checkpoint_retries = checkpoint_retries
        self.checkpoint_retry_delay_ms = checkpoint_retry_delay_ms

    @staticmethod
    def load_artifact(path: str | Path) -> CapabilityArtifact:
        return CapabilityArtifact.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )

    def run(
        self,
        artifact: CapabilityArtifact,
        inputs: dict[str, Any],
    ) -> RunResult:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = self.evidence_dir / f"{artifact.name}_{run_id}.jsonl"
        evidence: list[str] = [str(log_path)]
        recovered_conditions = 0
        handoffs_completed = 0

        self._write_event(
            log_path,
            {
                "event": "run_started",
                "capability": artifact.name,
                "artifact_version": artifact.artifact_version,
                "input_names": sorted(inputs.keys()),
            },
        )

        try:
            normalized_inputs = self._validate_inputs(artifact, inputs)
        except (TypeError, ValueError) as exc:
            self._write_event(
                log_path,
                {
                    "event": "hard_failure",
                    "code": "INVALID_INPUT",
                    "message": str(exc),
                },
            )
            return RunResult(
                status=RunStatus.FAILURE,
                capability_name=artifact.name,
                code="INVALID_INPUT",
                message=f"Invalid invocation inputs: {exc}",
                evidence=evidence,
            )

        try:
            entry_url = self._resolve_string(
                artifact.entry_url,
                normalized_inputs,
            )
            assert entry_url is not None

            blocked = self._check_navigation_policy(
                url=entry_url,
                artifact=artifact,
                log_path=log_path,
                evidence=evidence,
                failed_step="entry_url",
            )
            if blocked is not None:
                return blocked

            self.surface.open(entry_url)

            blocked = self._check_current_url_policy(
                artifact=artifact,
                log_path=log_path,
                evidence=evidence,
                failed_step="entry_url",
            )
            if blocked is not None:
                return blocked

            for step in artifact.steps:
                resolved_step = self._resolve_step(
                    step,
                    normalized_inputs,
                )

                self._write_event(
                    log_path,
                    {
                        "event": "step_started",
                        "step_id": resolved_step.id,
                        "action": resolved_step.action.type.value,
                    },
                )

                skip_execution = False

                if self.policy is not None:
                    policy_decision = self.policy.evaluate_action(
                        action=resolved_step.action.type,
                        target=resolved_step.target,
                        value=resolved_step.action.value,
                    )

                    if policy_decision.disposition == PolicyDisposition.BLOCK:
                        self._write_event(
                            log_path,
                            {
                                "event": "policy_blocked",
                                "step_id": resolved_step.id,
                                "reason": policy_decision.reason,
                            },
                        )
                        failure_evidence = self._capture_failure(
                            artifact.name,
                            resolved_step.id,
                        )
                        return RunResult(
                            status=RunStatus.FAILURE,
                            capability_name=artifact.name,
                            code="POLICY_BLOCKED",
                            failed_step=resolved_step.id,
                            message=policy_decision.reason,
                            evidence=evidence + failure_evidence,
                        )

                    if policy_decision.disposition == PolicyDisposition.ESCALATE:
                        self._write_event(
                            log_path,
                            {
                                "event": "policy_escalation",
                                "step_id": resolved_step.id,
                                "reason": policy_decision.reason,
                            },
                        )

                        if self.handoff is None:
                            escalation_evidence = self._capture_failure(
                                artifact.name,
                                resolved_step.id,
                            )
                            return RunResult(
                                status=RunStatus.ESCALATED,
                                capability_name=artifact.name,
                                code="HUMAN_REQUIRED",
                                failed_step=resolved_step.id,
                                message=policy_decision.reason,
                                evidence=evidence + escalation_evidence,
                            )

                        handoff_result = self.handoff.handle(
                            surface=self.surface,
                            capability_name=artifact.name,
                            step=resolved_step,
                            reason=policy_decision.reason,
                        )
                        evidence.extend(handoff_result.evidence)

                        if not handoff_result.resumed:
                            self._write_event(
                                log_path,
                                {
                                    "event": "handoff_stopped",
                                    "step_id": resolved_step.id,
                                },
                            )
                            return RunResult(
                                status=RunStatus.ESCALATED,
                                capability_name=artifact.name,
                                code="HUMAN_ABORTED",
                                failed_step=resolved_step.id,
                                message="Human handoff was not resumed.",
                                evidence=evidence,
                            )

                        handoffs_completed += 1
                        skip_execution = (
                            handoff_result.action_completed_by_human
                        )
                        self._write_event(
                            log_path,
                            {
                                "event": "handoff_completed",
                                "step_id": resolved_step.id,
                                "action_completed_by_human": skip_execution,
                            },
                        )

                if not skip_execution:
                    try:
                        self._execute_step(resolved_step)
                    except Exception as exc:
                        outcome = self._detect_business_outcome(artifact)
                        if outcome:
                            self._write_event(
                                log_path,
                                {
                                    "event": "business_outcome",
                                    "code": outcome.code,
                                    "step_id": resolved_step.id,
                                },
                            )
                            return outcome.model_copy(
                                update={"evidence": evidence}
                            )

                        failure_evidence = self._capture_failure(
                            artifact.name,
                            resolved_step.id,
                        )
                        self._write_event(
                            log_path,
                            {
                                "event": "hard_failure",
                                "code": "STEP_EXECUTION_FAILED",
                                "step_id": resolved_step.id,
                                "message": str(exc),
                            },
                        )
                        return RunResult(
                            status=RunStatus.FAILURE,
                            capability_name=artifact.name,
                            code="STEP_EXECUTION_FAILED",
                            failed_step=resolved_step.id,
                            message=f"Step execution failed: {exc}",
                            evidence=evidence + failure_evidence,
                        )

                blocked = self._check_current_url_policy(
                    artifact=artifact,
                    log_path=log_path,
                    evidence=evidence,
                    failed_step=resolved_step.id,
                )
                if blocked is not None:
                    return blocked

                outcome = self._detect_business_outcome(artifact)
                if outcome:
                    self._write_event(
                        log_path,
                        {
                            "event": "business_outcome",
                            "code": outcome.code,
                            "step_id": resolved_step.id,
                        },
                    )
                    return outcome.model_copy(
                        update={"evidence": evidence}
                    )

                if resolved_step.checkpoint:
                    met, recovered = self._checkpoint_met_with_retry(
                        resolved_step.checkpoint,
                        log_path=log_path,
                        step_id=resolved_step.id,
                    )
                    recovered_conditions += int(recovered)

                    if not met:
                        outcome = self._detect_business_outcome(artifact)
                        if outcome:
                            self._write_event(
                                log_path,
                                {
                                    "event": "business_outcome",
                                    "code": outcome.code,
                                    "step_id": resolved_step.id,
                                },
                            )
                            return outcome.model_copy(
                                update={"evidence": evidence}
                            )

                        failure_evidence = self._capture_failure(
                            artifact.name,
                            resolved_step.id,
                        )
                        self._write_event(
                            log_path,
                            {
                                "event": "hard_failure",
                                "code": "CHECKPOINT_FAILED",
                                "step_id": resolved_step.id,
                            },
                        )
                        return RunResult(
                            status=RunStatus.FAILURE,
                            capability_name=artifact.name,
                            code="CHECKPOINT_FAILED",
                            failed_step=resolved_step.id,
                            message=(
                                f"Checkpoint failed after '{resolved_step.id}': "
                                f"{resolved_step.checkpoint.description or resolved_step.checkpoint.type.value}"
                            ),
                            evidence=evidence + failure_evidence,
                        )

                self._write_event(
                    log_path,
                    {
                        "event": "step_completed",
                        "step_id": resolved_step.id,
                    },
                )

            final_met, final_recovered = self._checkpoint_met_with_retry(
                artifact.success_checkpoint,
                log_path=log_path,
                step_id="final_checkpoint",
            )
            recovered_conditions += int(final_recovered)

            if not final_met:
                outcome = self._detect_business_outcome(artifact)
                if outcome:
                    self._write_event(
                        log_path,
                        {
                            "event": "business_outcome",
                            "code": outcome.code,
                            "step_id": "final_checkpoint",
                        },
                    )
                    return outcome.model_copy(
                        update={"evidence": evidence}
                    )

                failure_evidence = self._capture_failure(
                    artifact.name,
                    "final_checkpoint",
                )
                self._write_event(
                    log_path,
                    {
                        "event": "hard_failure",
                        "code": "FINAL_CHECKPOINT_FAILED",
                    },
                )
                return RunResult(
                    status=RunStatus.FAILURE,
                    capability_name=artifact.name,
                    code="FINAL_CHECKPOINT_FAILED",
                    failed_step="final_checkpoint",
                    message="Final success checkpoint was not satisfied.",
                    evidence=evidence + failure_evidence,
                )

            message_parts: list[str] = []
            if recovered_conditions:
                message_parts.append(
                    f"Recovered from {recovered_conditions} transient checkpoint condition(s)."
                )
            if handoffs_completed:
                message_parts.append(
                    f"Completed {handoffs_completed} human handoff(s) in the same live session."
                )

            self._write_event(
                log_path,
                {
                    "event": "run_complete",
                    "status": RunStatus.SUCCESS.value,
                    "recovered_conditions": recovered_conditions,
                    "handoffs_completed": handoffs_completed,
                },
            )

            return RunResult(
                status=RunStatus.SUCCESS,
                capability_name=artifact.name,
                outputs=self._success_outputs(artifact),
                message=" ".join(message_parts) or None,
                evidence=evidence,
            )

        except Exception as exc:
            failure_evidence = self._capture_failure(
                artifact.name,
                "run",
            )
            self._write_event(
                log_path,
                {
                    "event": "hard_failure",
                    "code": "REPLAY_FAILED",
                    "message": str(exc),
                },
            )
            return RunResult(
                status=RunStatus.FAILURE,
                capability_name=artifact.name,
                code="REPLAY_FAILED",
                message=f"Replay failed: {exc}",
                evidence=evidence + failure_evidence,
            )

    def _check_navigation_policy(
        self,
        *,
        url: str,
        artifact: CapabilityArtifact,
        log_path: Path,
        evidence: list[str],
        failed_step: str,
    ) -> RunResult | None:
        if self.policy is None:
            return None

        decision = self.policy.evaluate_navigation(url)
        if decision.disposition != PolicyDisposition.BLOCK:
            return None

        self._write_event(
            log_path,
            {
                "event": "policy_blocked",
                "step_id": failed_step,
                "reason": decision.reason,
            },
        )
        return RunResult(
            status=RunStatus.FAILURE,
            capability_name=artifact.name,
            code="POLICY_BLOCKED",
            failed_step=failed_step,
            message=decision.reason,
            evidence=evidence,
        )

    def _check_current_url_policy(
        self,
        *,
        artifact: CapabilityArtifact,
        log_path: Path,
        evidence: list[str],
        failed_step: str,
    ) -> RunResult | None:
        if self.policy is None:
            return None

        decision = self.policy.evaluate_current_url(
            self.surface.current_url
        )
        if decision.disposition != PolicyDisposition.BLOCK:
            return None

        failure_evidence = self._capture_failure(
            artifact.name,
            failed_step,
        )
        self._write_event(
            log_path,
            {
                "event": "policy_blocked",
                "step_id": failed_step,
                "reason": decision.reason,
            },
        )
        return RunResult(
            status=RunStatus.FAILURE,
            capability_name=artifact.name,
            code="POLICY_BLOCKED",
            failed_step=failed_step,
            message=decision.reason,
            evidence=evidence + failure_evidence,
        )

    def _checkpoint_met_with_retry(
        self,
        checkpoint: Checkpoint,
        *,
        log_path: Path,
        step_id: str,
    ) -> tuple[bool, bool]:
        recovered = False

        for attempt in range(self.checkpoint_retries + 1):
            if self._checkpoint_met(checkpoint):
                if attempt > 0:
                    recovered = True
                    self._write_event(
                        log_path,
                        {
                            "event": "recoverable_condition_recovered",
                            "step_id": step_id,
                            "condition": "checkpoint_not_ready",
                            "attempt": attempt + 1,
                        },
                    )
                return True, recovered

            if attempt < self.checkpoint_retries:
                self._write_event(
                    log_path,
                    {
                        "event": "recoverable_condition",
                        "step_id": step_id,
                        "condition": "checkpoint_not_ready",
                        "attempt": attempt + 1,
                        "next_action": "wait_and_retry",
                    },
                )
                self.surface.wait(self.checkpoint_retry_delay_ms)

        return False, recovered

    def _validate_inputs(
        self,
        artifact: CapabilityArtifact,
        supplied: dict[str, Any],
    ) -> dict[str, Any]:
        definitions = {item.name: item for item in artifact.inputs}
        unknown = sorted(set(supplied) - set(definitions))
        if unknown:
            raise ValueError(f"Unknown input(s): {', '.join(unknown)}")

        normalized: dict[str, Any] = {}
        for definition in artifact.inputs:
            if definition.name not in supplied:
                if definition.required:
                    raise ValueError(
                        f"Missing required input '{definition.name}'."
                    )
                continue
            normalized[definition.name] = self._validate_input_value(
                definition,
                supplied[definition.name],
            )
        return normalized

    def _validate_input_value(
        self,
        definition: InputParameter,
        value: Any,
    ) -> Any:
        if definition.type == ParameterType.STRING:
            if not isinstance(value, str):
                raise TypeError(
                    f"'{definition.name}' must be a string."
                )
            return value

        if definition.type == ParameterType.INTEGER:
            if isinstance(value, bool):
                raise TypeError(
                    f"'{definition.name}' must be an integer."
                )
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise TypeError(
                    f"'{definition.name}' must be an integer."
                ) from exc

        if definition.type == ParameterType.NUMBER:
            if isinstance(value, bool):
                raise TypeError(
                    f"'{definition.name}' must be a number."
                )
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise TypeError(
                    f"'{definition.name}' must be a number."
                ) from exc

        if definition.type == ParameterType.BOOLEAN:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in {
                "true",
                "false",
            }:
                return value.lower() == "true"
            raise TypeError(
                f"'{definition.name}' must be a boolean."
            )

        if definition.type == ParameterType.ENUM:
            if not isinstance(value, str):
                raise TypeError(
                    f"'{definition.name}' must be a string enum value."
                )
            allowed = definition.allowed_values or []
            canonical = {item.lower(): item for item in allowed}
            if value.lower() not in canonical:
                raise ValueError(
                    f"'{definition.name}' must be one of: "
                    f"{', '.join(allowed)}."
                )
            return canonical[value.lower()]

        return value

    def _resolve_string(
        self,
        value: str | None,
        inputs: dict[str, Any],
    ) -> str | None:
        if value is None:
            return None

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in inputs:
                raise ValueError(
                    f"Missing value for placeholder '{name}'."
                )
            return str(inputs[name])

        return _PLACEHOLDER.sub(replace, value)

    def _resolve_target(
        self,
        target: Target | None,
        inputs: dict[str, Any],
    ) -> Target | None:
        if target is None:
            return None

        update: dict[str, Any] = {}
        for field in (
            "role",
            "name",
            "label",
            "text",
            "css",
            "xpath",
            "description",
        ):
            value = getattr(target, field)
            if isinstance(value, str):
                update[field] = self._resolve_string(value, inputs)

        if target.stable_attribute is not None:
            update["stable_attribute"] = {
                key: self._resolve_string(value, inputs)
                for key, value in target.stable_attribute.items()
            }

        return target.model_copy(update=update)

    def _resolve_checkpoint(
        self,
        checkpoint: Checkpoint | None,
        inputs: dict[str, Any],
    ) -> Checkpoint | None:
        if checkpoint is None:
            return None

        return checkpoint.model_copy(
            update={
                "value": self._resolve_string(
                    checkpoint.value,
                    inputs,
                ),
                "target": self._resolve_target(
                    checkpoint.target,
                    inputs,
                ),
            }
        )

    def _resolve_step(
        self,
        step: Step,
        inputs: dict[str, Any],
    ) -> Step:
        action = step.action.model_copy(
            update={
                "value": self._resolve_string(
                    step.action.value,
                    inputs,
                ),
            }
        )
        return step.model_copy(
            update={
                "action": action,
                "target": self._resolve_target(
                    step.target,
                    inputs,
                ),
                "checkpoint": self._resolve_checkpoint(
                    step.checkpoint,
                    inputs,
                ),
            }
        )

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
            self.surface.type(
                target,
                action.value,
                action.timeout_ms,
            )
        elif action.type == ActionType.SELECT:
            assert target is not None
            if action.value is None:
                raise ValueError("select action requires a value.")
            self.surface.select(
                target,
                action.value,
                action.timeout_ms,
            )
        elif action.type == ActionType.READ:
            assert target is not None
            self.surface.read(target, action.timeout_ms)
        elif action.type == ActionType.WAIT:
            self.surface.wait(action.timeout_ms)
        elif action.type == ActionType.NAVIGATE:
            if action.value is None:
                raise ValueError(
                    "navigate action requires a URL in action.value."
                )
            self.surface.open(action.value)
        else:
            raise ValueError(
                f"Unsupported action type: {action.type}"
            )

    def _checkpoint_met(self, checkpoint: Checkpoint) -> bool:
        if checkpoint.type == CheckpointType.TEXT_PRESENT:
            assert checkpoint.value is not None
            return self.surface.is_visible(
                Target(text=checkpoint.value),
                timeout_ms=5000,
            )
        if checkpoint.type == CheckpointType.ELEMENT_VISIBLE:
            assert checkpoint.target is not None
            return self.surface.is_visible(
                checkpoint.target,
                timeout_ms=5000,
            )
        if checkpoint.type == CheckpointType.URL_CONTAINS:
            assert checkpoint.value is not None
            return checkpoint.value in self.surface.current_url
        return False

    def _detect_business_outcome(
        self,
        artifact: CapabilityArtifact,
    ) -> RunResult | None:
        for code in artifact.known_business_outcomes:
            if self.surface.is_visible(
                Target(text=f"OUTCOME: {code}"),
                timeout_ms=150,
            ):
                return RunResult(
                    status=RunStatus.BUSINESS_OUTCOME,
                    capability_name=artifact.name,
                    code=code,
                    message=f"Known business outcome detected: {code}",
                )
        return None

    def _capture_failure(
        self,
        capability_name: str,
        step_id: str,
    ) -> list[str]:
        try:
            path = (
                self.evidence_dir
                / f"{capability_name}_{step_id}.png"
            )
            return [self.surface.screenshot(path)]
        except Exception:
            return []

    def _success_outputs(
        self,
        artifact: CapabilityArtifact,
    ) -> dict[str, Any]:
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

    @staticmethod
    def _write_event(path: Path, event: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(event, ensure_ascii=False) + "\n"
            )
