from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import DiscoveryRunner, OpenAIDecisionModel  # noqa: E402
from src.artifact.models import Checkpoint, CheckpointType  # noqa: E402
from src.surface import PlaywrightSurface  # noqa: E402


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a genuine LLM-driven computer-use discovery session."
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

    surface = PlaywrightSurface(headless=not args.headed)
    model = OpenAIDecisionModel(model=args.model)

    runner = DiscoveryRunner(
        surface=surface,
        decision_model=model,
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value=args.success_text,
            description="Configured discovery success checkpoint.",
        ),
    )

    try:
        result = runner.run(
            goal=args.goal,
            inputs=inputs,
            entry_url=args.entry_url,
            max_steps=args.max_steps,
        )

        print(result.model_dump_json(indent=2))
        return 0 if result.status.value == "success" else 1
    finally:
        surface.close()


if __name__ == "__main__":
    raise SystemExit(main())
