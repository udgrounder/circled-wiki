"""Resolve the repository without persisting any machine-specific paths."""

from pathlib import Path
from typing import Optional


def project_root(start: Optional[Path] = None) -> Path:
    """Find a source repository or an installed Circled Wiki project root."""
    candidate = (start or Path.cwd()).resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / "pyproject.toml").is_file() and (directory / "src" / "circled_wiki").is_dir():
            return directory
        if (directory / "knowledge").is_dir() and (
            (directory / ".circled-wiki").is_dir() or (directory / "docs").is_dir()
        ):
            return directory
    raise FileNotFoundError("Circled Wiki source repository or installed project root was not found")
