from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.artifact.models import (  # noqa: E402
    Action,
    ActionType,
    Checkpoint,
    CheckpointType,
    Step,
    Target,
)
from src.replay import ReplayEngine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a replay artifact that reaches the review page and then "
            "attempts a simulated irreversible action for human-handoff testing."
        )
    )
    parser.add_argument(
        "--source",
        default="artifacts/open_sub_account_discovered_v1.json",
    )
    parser.add_argument(
        "--output",
        default="artifacts/open_sub_account_handoff_demo_v1.json",
    )
    args = parser.parse_args()

    artifact = ReplayEngine.load_artifact(ROOT / args.source)

    risky_step = Step(
        id="step_human_final_approval",
        description=(
            "Simulated irreversible final account creation. "
            "Execution policy must require a human handoff."
        ),
        action=Action(type=ActionType.CLICK),
        target=Target(
            role="button",
            name="Create Account",
            description="Simulated final account creation",
        ),
    )

    updated = artifact.model_copy(
        update={
            "artifact_version": f"{artifact.artifact_version}-handoff-demo",
            "description": (
                artifact.description
                + " This demo variant includes a simulated final action "
                  "that must be completed by a human."
            ),
            "steps": [*artifact.steps, risky_step],
            "success_checkpoint": Checkpoint(
                type=CheckpointType.TEXT_PRESENT,
                value="CHECKPOINT: ACCOUNT_CREATED",
                description=(
                    "Confirms the human completed the simulated final action."
                ),
            ),
        }
    )

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        updated.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
