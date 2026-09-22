from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.handoff import ConsoleHandoff  # noqa: E402
from src.replay import ReplayEngine  # noqa: E402
from src.safety import ExecutionPolicy  # noqa: E402
from src.surface import PlaywrightSurface  # noqa: E402


def parse_inputs(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(
                f"Invalid --input '{item}'. Expected key=value."
            )
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("Input name cannot be empty.")
        parsed[key] = value
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically replay a saved computer-use capability "
            "with policy guardrails and optional same-session human handoff."
        )
    )
    parser.add_argument("--artifact", required=True)
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Capability input in key=value form. Repeat for multiple inputs.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help=(
            "Show the browser. Required to manually complete a risky action "
            "during human handoff."
        ),
    )
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=None,
        help=(
            "Explicit allowed origin. Repeat to allow more than one. "
            "Defaults to http://127.0.0.1:8000."
        ),
    )
    parser.add_argument(
        "--checkpoint-retries",
        type=int,
        default=1,
        help="Number of deterministic retries for a checkpoint that is not ready.",
    )

    args = parser.parse_args()

    try:
        inputs = parse_inputs(args.input)
    except ValueError as exc:
        parser.error(str(exc))

    artifact = ReplayEngine.load_artifact(args.artifact)
    surface = PlaywrightSurface(headless=not args.headed)

    allowed_origins = set(
        args.allow_origin or ["http://127.0.0.1:8000"]
    )
    policy = ExecutionPolicy(
        allowed_origins=allowed_origins,
    )

    # In headless mode a risky action returns status=escalated instead of
    # silently auto-approving it. In headed mode the same Playwright session
    # remains open for human takeover.
    handoff = ConsoleHandoff() if args.headed else None

    try:
        engine = ReplayEngine(
            surface,
            policy=policy,
            handoff=handoff,
            checkpoint_retries=args.checkpoint_retries,
        )
        result = engine.run(artifact, inputs)
        print(result.model_dump_json(indent=2))

        if result.status.value in {"success", "business_outcome"}:
            return 0
        if result.status.value == "escalated":
            return 2
        return 1
    finally:
        surface.close()


if __name__ == "__main__":
    raise SystemExit(main())
