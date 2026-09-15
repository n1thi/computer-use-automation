from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.replay import ReplayEngine  # noqa: E402
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
        description="Deterministically replay a saved computer-use capability."
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
        help="Show the browser window while replay runs.",
    )
    args = parser.parse_args()

    try:
        inputs = parse_inputs(args.input)
    except ValueError as exc:
        parser.error(str(exc))

    artifact = ReplayEngine.load_artifact(args.artifact)
    surface = PlaywrightSurface(headless=not args.headed)

    try:
        engine = ReplayEngine(surface)
        result = engine.run(artifact, inputs)
        print(result.model_dump_json(indent=2))
        return 0 if result.status.value in {"success", "business_outcome"} else 1
    finally:
        surface.close()


if __name__ == "__main__":
    raise SystemExit(main())
