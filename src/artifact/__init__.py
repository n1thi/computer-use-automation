__all__ = [
    "Action",
    "ActionType",
    "ArtifactRecorder",
    "ArtifactRecordingSpec",
    "CapabilityArtifact",
    "Checkpoint",
    "CheckpointType",
    "InputParameter",
    "OutputParameter",
    "ParameterType",
    "RunResult",
    "RunStatus",
    "Step",
    "Target",
]


def __getattr__(name: str):
    if name in {"Action", "ActionType", "CapabilityArtifact", "Checkpoint", "CheckpointType", "InputParameter", "OutputParameter", "ParameterType", "RunResult", "RunStatus", "Step", "Target"}:
        from .models import (
            Action,
            ActionType,
            CapabilityArtifact,
            Checkpoint,
            CheckpointType,
            InputParameter,
            OutputParameter,
            ParameterType,
            RunResult,
            RunStatus,
            Step,
            Target,
        )

        return {
            "Action": Action,
            "ActionType": ActionType,
            "CapabilityArtifact": CapabilityArtifact,
            "Checkpoint": Checkpoint,
            "CheckpointType": CheckpointType,
            "InputParameter": InputParameter,
            "OutputParameter": OutputParameter,
            "ParameterType": ParameterType,
            "RunResult": RunResult,
            "RunStatus": RunStatus,
            "Step": Step,
            "Target": Target,
        }[name]
    if name in {"ArtifactRecorder", "ArtifactRecordingSpec"}:
        from .recorder import ArtifactRecorder, ArtifactRecordingSpec

        return {
            "ArtifactRecorder": ArtifactRecorder,
            "ArtifactRecordingSpec": ArtifactRecordingSpec,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
