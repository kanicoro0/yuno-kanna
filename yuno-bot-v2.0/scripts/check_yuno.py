from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMMANDS: list[list[str]] = [
    [sys.executable, "-m", "compileall", "main.py", "yuno", "tests"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
    [
        sys.executable,
        "-c",
        "from yuno.app import create_bot; bot=create_bot(); print('bot ok')",
    ],
]


def run(command: list[str]) -> None:
    print("\n$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    for command in COMMANDS:
        run(command)
    print("\nAll yuno checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
