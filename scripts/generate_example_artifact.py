from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.artifact.models import (
    Action, ActionType, CapabilityArtifact, Checkpoint, CheckpointType,
    InputParameter, OutputParameter, ParameterType, Step, Target,
)


def build_example_artifact() -> CapabilityArtifact:
    return CapabilityArtifact(
        artifact_version="1.0",
        name="open_sub_account",
        description=(
            "Search for a member, open the new sub-account flow, choose an account "
            "type, and reach the review screen without performing the irreversible "
            "final account-creation action."
        ),
        target_application="mock_credit_union",
        entry_url="http://127.0.0.1:8000",
        inputs=[
            InputParameter(
                name="member_id",
                type=ParameterType.STRING,
                description="Member identifier used for lookup.",
                required=True,
                sensitive=True,
            ),
            InputParameter(
                name="account_type",
                type=ParameterType.ENUM,
                description="Type of sub-account to open.",
                required=True,
                allowed_values=["checking", "savings"],
            ),
        ],
        outputs=[
            OutputParameter(
                name="review_status",
                type=ParameterType.STRING,
                description="Status after reaching the review checkpoint.",
            )
        ],
        steps=[
            Step(
                id="step_1",
                description="Enter the member identifier.",
                action=Action(type=ActionType.TYPE, value="${member_id}"),
                target=Target(role="textbox", name="Member ID"),
            ),
            Step(
                id="step_2",
                description="Search for the member.",
                action=Action(type=ActionType.CLICK),
                target=Target(role="button", name="Search Member"),
                checkpoint=Checkpoint(
                    type=CheckpointType.ELEMENT_VISIBLE,
                    target=Target(role="link", name="Open New Sub-account"),
                    description="Member detail page loaded.",
                ),
            ),
            Step(
                id="step_3",
                description="Open the new sub-account workflow.",
                action=Action(type=ActionType.CLICK),
                target=Target(role="link", name="Open New Sub-account"),
                checkpoint=Checkpoint(
                    type=CheckpointType.TEXT_PRESENT,
                    value="Open Sub-account",
                    description="New sub-account form is visible.",
                ),
            ),
            Step(
                id="step_4",
                description="Choose the requested account type.",
                action=Action(type=ActionType.CLICK),
                target=Target(
                    role="radio",
                    name="${account_type}",
                    description="Semantic name resolved from the invocation parameter.",
                ),
            ),
            Step(
                id="step_5",
                description="Continue to the review screen.",
                action=Action(type=ActionType.CLICK),
                target=Target(role="button", name="Continue"),
            ),
        ],
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value="CHECKPOINT: REVIEW_READY",
            description="Confirms the workflow reached the review page.",
        ),
        known_business_outcomes=["MEMBER_NOT_FOUND"],
    )


def main() -> None:
    artifact = build_example_artifact()
    output_dir = ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "open_sub_account_v1.json"
    output_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote artifact to {output_path}")
    print(artifact.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
