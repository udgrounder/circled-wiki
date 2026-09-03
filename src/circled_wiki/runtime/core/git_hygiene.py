"""Read-only detection of generated artifacts already tracked by Git."""

from pathlib import Path
import subprocess
from typing import Dict, List


_GENERATED_MARKERS = ("/.runtime/", "/.raw/", "__pycache__/", ".circled-wiki-backups/", ".DS_Store", ".pytest_cache/")
_CURATION_QUEUE_PREFIX = "workspace/task/curation_reconciliation/"


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


def verify_curation_completion_staging(project_root: Path) -> Dict[str, object]:
    """Report staged completed Curation task deletions without changing Git."""
    result = subprocess.run(
        [
            "git", "-C", str(project_root), "-c", "core.quotepath=false",
            "diff", "--cached", "--name-status", "--no-renames", "--",
            _CURATION_QUEUE_PREFIX,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    active_deletions: Dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status = fields[0].strip()
        path = fields[-1].strip()
        if path.startswith(_CURATION_QUEUE_PREFIX) and status == "D":
            active_deletions[path] = status
    return {
        "passed": True,
        "status": "passed",
        "checked_count": len(active_deletions),
        "completed_task_deletions": sorted(active_deletions),
        "recovery": "Completed Curation task deletions are valid.",
    }
