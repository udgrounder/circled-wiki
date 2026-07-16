"""Resolve the repository without persisting any machine-specific paths."""

from pathlib import Path
from typing import Optional


def project_root(start: Optional[Path] = None) -> Path:
    """Find a source repository or an installed Knowledge OS project root."""
    candidate = (start or Path.cwd()).resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / "knowledge").is_dir() and (
            (directory / ".knowledge-os").is_dir() or (directory / "docs").is_dir()
        ):
            return directory
    raise FileNotFoundError("project root containing knowledge/ and .knowledge-os/ was not found")
