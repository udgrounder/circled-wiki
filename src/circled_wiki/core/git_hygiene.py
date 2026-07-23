"""Read-only detection of generated artifacts already tracked by Git."""

from pathlib import Path
import subprocess
from typing import Dict, List


_GENERATED_MARKERS = ("/.runtime/", "/.raw/", "__pycache__/", ".circled-wiki-backups/", ".DS_Store", ".pytest_cache/")


def tracked_generated_artifacts(project_root: Path) -> List[Dict[str, str]]:
    """Return tracked generated files; never untrack or modify the working tree."""
    result = subprocess.run(
        ["git", "-C", str(project_root), "ls-files"], capture_output=True, text=True, check=True
    )
    findings: List[Dict[str, str]] = []
    for path in result.stdout.splitlines():
        normalized = "/" + path
        marker = next((item for item in _GENERATED_MARKERS if item in normalized or path.endswith(item)), None)
        if marker:
            findings.append({"path": path, "marker": marker})
    return findings
