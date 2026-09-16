from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.surface import PlaywrightSurface  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the compact page observation used by discovery."
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Page to inspect.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium while inspecting.",
    )
    args = parser.parse_args()

    surface = PlaywrightSurface(headless=not args.headed)

    try:
        surface.open(args.url)
        observation = surface.observe()
        print(observation.model_dump_json(indent=2))
        return 0
    finally:
        surface.close()


if __name__ == "__main__":
    raise SystemExit(main())
