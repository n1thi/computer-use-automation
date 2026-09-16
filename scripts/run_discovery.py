from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import DiscoveryRunner, DiscoveryStatus, OpenAIDecisionModel  # noqa: E402
from src.artifact import (  # noqa: E402
    ArtifactRecorder,
    ArtifactRecordingSpec,
    Checkpoint,
    CheckpointType,
    InputParameter,
    OutputParameter,
    ParameterType,
)
from src.surface import PlaywrightSurface  # noqa: E402


DEFAULT_ARTIFACT_PATH = "artifacts/open_sub_account_discovered_v1.json"


def parse_inputs(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}

    for item in values:
        if "=" not in item:
            raise ValueError(f"Invalid --input '{item}'. Expected key=value.")

        key, value = item.split("=", 1)
        key = key.strip()

        if not key:
            raise ValueError("Input name cannot be empty.")

        parsed[key] = value

    return parsed


def build_open_sub_account_recording_spec(
    *,
    entry_url: str,
    success_text: str,
) -> ArtifactRecordingSpec:
    return ArtifactRecordingSpec(
        artifact_version="1.0",
        name="open_sub_account",
        description=(
            "Search for a member, open the new sub-account flow, choose an "
            "account type, and reach the review screen without performing the "
            "irreversible final account-creation action."
        ),
        target_application="mock_credit_union",
        entry_url=entry_url,
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
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value=success_text,
            description="Confirms the workflow reached the review page.",
        ),
        known_business_outcomes=["MEMBER_NOT_FOUND"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run an LLM-driven discovery session and record a reusable artifact "
            "when discovery succeeds."
        )
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Invocation input in key=value form. Repeat as needed.",
    )
    parser.add_argument(
        "--entry-url",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--success-text",
        default="CHECKPOINT: REVIEW_READY",
    )
    parser.add_argument(
        "--artifact-out",
        default=DEFAULT_ARTIFACT_PATH,
        help="Where to save the discovered reusable capability.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
    )
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--headed", action="store_true")

    args = parser.parse_args()

    try:
        inputs = parse_inputs(args.input)
    except ValueError as exc:
        parser.error(str(exc))

    if not os.getenv("OPENAI_API_KEY"):
        parser.error(
            "OPENAI_API_KEY is not set. Export it in the shell before running."
        )

    success_checkpoint = Checkpoint(
        type=CheckpointType.TEXT_PRESENT,
        value=args.success_text,
        description="Configured discovery success checkpoint.",
    )

    surface = PlaywrightSurface(headless=not args.headed)
    model = OpenAIDecisionModel(model=args.model)

    runner = DiscoveryRunner(
        surface=surface,
        decision_model=model,
        success_checkpoint=success_checkpoint,
    )

    try:
        result = runner.run(
            goal=args.goal,
            inputs=inputs,
            entry_url=args.entry_url,
            max_steps=args.max_steps,
        )

        if result.status == DiscoveryStatus.SUCCESS:
            recorder = ArtifactRecorder()
            spec = build_open_sub_account_recording_spec(
                entry_url=args.entry_url,
                success_text=args.success_text,
            )

            artifact = recorder.record(
                decisions=result.decisions,
                invocation_inputs=inputs,
                spec=spec,
            )

            artifact_path = recorder.save(
                artifact,
                ROOT / args.artifact_out,
            )

            result = result.model_copy(
                update={"artifact_path": str(artifact_path)}
            )

        print(result.model_dump_json(indent=2))
        return 0 if result.status == DiscoveryStatus.SUCCESS else 1

    finally:
        surface.close()


if __name__ == "__main__":
    raise SystemExit(main())
