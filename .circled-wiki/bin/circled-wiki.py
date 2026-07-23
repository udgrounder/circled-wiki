#!/usr/bin/env python3
"""Portable Circled Wiki CLI launcher for an installed project."""

import os
import sys
from pathlib import Path


OS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = OS_ROOT.parent
sys.path.insert(0, str(OS_ROOT / "runtime"))
os.chdir(PROJECT_ROOT)

try:
    from circled_wiki.cli.__main__ import run_cli
except ModuleNotFoundError as error:
    if error.name == "yaml":
        raise SystemExit(
            "Circled Wiki requires PyYAML. Install it with: python3 -m pip install PyYAML"
        ) from error
    raise


if __name__ == "__main__":
    raise SystemExit(run_cli())
