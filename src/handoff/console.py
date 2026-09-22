from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.artifact.models import Step
from src.handoff.base import HandoffResult
from src.surface.base import Surface


class ConsoleHandoff:
    """Pause automation while a person controls the same live browser session."""

    def __init__(
        self,
        *,
        evidence_dir: str | Path = "evidence/handoff",
        input_func: Callable[[str], str] = input,
    ) -> None:
        self.evidence_dir = Path(evidence_dir)
        self.input_func = input_func

    def handle(
        self,
        *,
        surface: Surface,
        capability_name: str,
        step: Step,
        reason: str,
    ) -> HandoffResult:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        log_path = self.evidence_dir / f"handoff_{run_id}.jsonl"
        before_path = self.evidence_dir / f"handoff_{run_id}_before.png"
        after_path = self.evidence_dir / f"handoff_{run_id}_after.png"

        evidence: list[str] = [str(log_path)]

        before_url = surface.current_url
        try:
            evidence.append(surface.screenshot(before_path))
        except Exception:
            pass

        target_summary = self._target_summary(step)

        self._write(
            log_path,
            {
                "event": "handoff_started",
                "capability": capability_name,
                "step_id": step.id,
                "action": step.action.type.value,
                "target": target_summary,
                "reason": reason,
                "url": before_url,
            },
        )

        print("\n=== HUMAN HANDOFF REQUIRED ===")
        print(reason)
        print(f"Paused at step: {step.id}")
        print(f"Intended action: {step.action.type.value} {target_summary}".strip())
        print(
            "Use the already-open browser window to complete this action. "
            "Automation will not perform the risky action itself."
        )

        response = self.input_func(
            "Press Enter after completing it, or type 'abort' to stop: "
        ).strip().casefold()

        if response == "abort":
            self._write(
                log_path,
                {
                    "event": "handoff_aborted",
                    "capability": capability_name,
                    "step_id": step.id,
                    "url": surface.current_url,
                },
            )
            return HandoffResult(
                resumed=False,
                action_completed_by_human=False,
                evidence=evidence,
            )

        after_url = surface.current_url
        try:
            evidence.append(surface.screenshot(after_path))
        except Exception:
            pass

        self._write(
            log_path,
            {
                "event": "human_action_completed",
                "capability": capability_name,
                "step_id": step.id,
                "action": step.action.type.value,
                "target": target_summary,
                "url_before": before_url,
                "url_after": after_url,
            },
        )
        self._write(
            log_path,
            {
                "event": "handoff_resumed",
                "capability": capability_name,
                "step_id": step.id,
                "url": after_url,
            },
        )

        return HandoffResult(
            resumed=True,
            action_completed_by_human=True,
            evidence=evidence,
        )

    @staticmethod
    def _target_summary(step: Step) -> str:
        target = step.target
        if target is None:
            return ""
        if target.role and target.name:
            return f"{target.role}:{target.name}"
        if target.label:
            return f"label:{target.label}"
        if target.text:
            return f"text:{target.text}"
        if target.description:
            return target.description
        return "target"

    @staticmethod
    def _write(path: Path, event: dict) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
