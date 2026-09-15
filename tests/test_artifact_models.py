from pathlib import Path

import pytest
from pydantic import ValidationError

from src.artifact.models import (
    Action, ActionType, CapabilityArtifact, Checkpoint, CheckpointType,
    InputParameter, OutputParameter, ParameterType, RunResult, RunStatus,
    Step, Target,
)


def build_minimal_artifact() -> CapabilityArtifact:
    return CapabilityArtifact(
        artifact_version="1.0",
        name="open_sub_account",
        description="Minimal artifact used for tests.",
        target_application="mock_credit_union",
        entry_url="http://127.0.0.1:8000",
        inputs=[
            InputParameter(name="member_id", type=ParameterType.STRING, sensitive=True),
            InputParameter(
                name="account_type",
                type=ParameterType.ENUM,
                allowed_values=["checking", "savings"],
            ),
        ],
        outputs=[OutputParameter(name="review_status", type=ParameterType.STRING)],
        steps=[
            Step(
                id="step_1",
                action=Action(type=ActionType.TYPE, value="${member_id}"),
                target=Target(role="textbox", name="Member ID"),
            ),
            Step(
                id="step_2",
                action=Action(type=ActionType.CLICK),
                target=Target(role="radio", name="${account_type}"),
            ),
        ],
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value="CHECKPOINT: REVIEW_READY",
        ),
        known_business_outcomes=["MEMBER_NOT_FOUND"],
    )


def test_artifact_round_trip():
    artifact = build_minimal_artifact()
    restored = CapabilityArtifact.model_validate_json(artifact.model_dump_json())
    assert restored.name == artifact.name
    assert restored.schema_version == "1.0"
    assert restored.steps[0].action.value == "${member_id}"
    assert restored.known_business_outcomes == ["MEMBER_NOT_FOUND"]


def test_generated_artifact_is_parameterized():
    path = Path("artifacts/open_sub_account_v1.json")
    assert path.exists(), "Run `python scripts/generate_example_artifact.py` first."
    text = path.read_text(encoding="utf-8")
    assert "${member_id}" in text
    assert "${account_type}" in text


def test_invalid_action_type_is_rejected():
    with pytest.raises(ValidationError):
        Action(type="launch_nuclear_missile")  # type: ignore[arg-type]


def test_target_requires_locator_information():
    with pytest.raises(ValidationError):
        Target()


def test_enum_input_requires_allowed_values():
    with pytest.raises(ValidationError):
        InputParameter(name="account_type", type=ParameterType.ENUM)


def test_duplicate_step_ids_are_rejected():
    step = Step(
        id="step_1",
        action=Action(type=ActionType.CLICK),
        target=Target(role="button", name="Continue"),
    )
    with pytest.raises(ValidationError):
        CapabilityArtifact(
            artifact_version="1.0",
            name="duplicate_steps",
            description="Invalid duplicate step IDs.",
            target_application="mock_credit_union",
            entry_url="http://127.0.0.1:8000",
            inputs=[],
            outputs=[],
            steps=[step, step],
            success_checkpoint=Checkpoint(
                type=CheckpointType.TEXT_PRESENT, value="done"
            ),
        )


def test_run_result_success_and_business_outcome():
    success = RunResult(
        status=RunStatus.SUCCESS,
        capability_name="open_sub_account",
        outputs={"review_status": "REVIEW_READY"},
    )
    not_found = RunResult(
        status=RunStatus.BUSINESS_OUTCOME,
        capability_name="open_sub_account",
        code="MEMBER_NOT_FOUND",
    )
    assert success.status == RunStatus.SUCCESS
    assert success.outputs["review_status"] == "REVIEW_READY"
    assert not_found.code == "MEMBER_NOT_FOUND"
