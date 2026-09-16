from src.agent.models import AgentDecision
from src.artifact import (
    ActionType,
    ArtifactRecorder,
    ArtifactRecordingSpec,
    CapabilityArtifact,
    Checkpoint,
    CheckpointType,
    InputParameter,
    OutputParameter,
    ParameterType,
    Target,
)


def build_spec() -> ArtifactRecordingSpec:
    return ArtifactRecordingSpec(
        name="open_sub_account",
        description="Test capability.",
        target_application="mock_credit_union",
        entry_url="http://127.0.0.1:8000",
        inputs=[
            InputParameter(
                name="member_id",
                type=ParameterType.STRING,
                sensitive=True,
            ),
            InputParameter(
                name="account_type",
                type=ParameterType.ENUM,
                allowed_values=["checking", "savings"],
            ),
        ],
        outputs=[
            OutputParameter(
                name="review_status",
                type=ParameterType.STRING,
            )
        ],
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value="CHECKPOINT: REVIEW_READY",
        ),
        known_business_outcomes=["MEMBER_NOT_FOUND"],
    )


def build_decisions() -> list[AgentDecision]:
    return [
        AgentDecision(
            action=ActionType.TYPE,
            target=Target(
                role="textbox",
                name="Member ID",
                label="Member ID",
            ),
            value="12345",
            reason="Enter member 12345.",
        ),
        AgentDecision(
            action=ActionType.CLICK,
            target=Target(
                role="radio",
                name="Savings",
                label="Savings",
            ),
            reason="Choose the savings account type.",
        ),
    ]


def test_recorder_parameterizes_discovery_values():
    artifact = ArtifactRecorder().record(
        decisions=build_decisions(),
        invocation_inputs={
            "member_id": "12345",
            "account_type": "savings",
        },
        spec=build_spec(),
    )

    assert artifact.steps[0].action.value == "${member_id}"
    assert artifact.steps[1].target is not None
    assert artifact.steps[1].target.name == "${account_type}"


def test_recorder_normalizes_redundant_target_fields():
    artifact = ArtifactRecorder().record(
        decisions=build_decisions(),
        invocation_inputs={
            "member_id": "12345",
            "account_type": "savings",
        },
        spec=build_spec(),
    )

    first_target = artifact.steps[0].target
    assert first_target is not None
    assert first_target.role == "textbox"
    assert first_target.name == "Member ID"
    assert first_target.label is None
    assert first_target.text is None


def test_recorder_parameterizes_descriptions():
    artifact = ArtifactRecorder().record(
        decisions=build_decisions(),
        invocation_inputs={
            "member_id": "12345",
            "account_type": "savings",
        },
        spec=build_spec(),
    )

    assert artifact.steps[0].description == "Enter member ${member_id}."
    assert artifact.steps[1].description == (
        "Choose the ${account_type} account type."
    )


def test_recorded_artifact_round_trips(tmp_path):
    recorder = ArtifactRecorder()
    artifact = recorder.record(
        decisions=build_decisions(),
        invocation_inputs={
            "member_id": "12345",
            "account_type": "savings",
        },
        spec=build_spec(),
    )

    path = recorder.save(artifact, tmp_path / "artifact.json")
    restored = CapabilityArtifact.model_validate_json(
        path.read_text(encoding="utf-8")
    )

    assert restored.name == "open_sub_account"
    assert restored.steps[0].action.value == "${member_id}"
    assert restored.steps[1].target is not None
    assert restored.steps[1].target.name == "${account_type}"
