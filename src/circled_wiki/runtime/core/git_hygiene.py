"""Read-only detection of generated artifacts already tracked by Git."""

from pathlib import Path
import subprocess
from typing import Dict, List


_GENERATED_MARKERS = ("/.runtime/", "/.raw/", "__pycache__/", ".circled-wiki-backups/", ".DS_Store", ".pytest_cache/")
_CURATION_QUEUE_PREFIX = "workspace/task/curation_reconciliation/"
_CURATION_ARCHIVE_PREFIX = "workspace/task/.archive/curation_reconciliation/"


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


def verify_curation_archive_transitions(project_root: Path) -> Dict[str, object]:
    """Verify that staged Curation Queue completions include their Archive pair.

    Curation completion intentionally stores the record in the documented
    sibling ``workspace/task/.archive`` tree.  Git's path-scoped staging can
    therefore contain the Queue deletion without the Archive addition.  This
    read-only Gate inspects only the index and never stages, unstages, or
    rewrites a user's files.
    """
    result = subprocess.run(
        [
            "git", "-C", str(project_root), "-c", "core.quotepath=false",
            "diff", "--cached", "--name-status", "--no-renames", "--",
            _CURATION_QUEUE_PREFIX, _CURATION_ARCHIVE_PREFIX,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    active_deletions: Dict[str, str] = {}
    archive_changes: Dict[str, str] = {}
    archive_additions: Dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status = fields[0].strip()
        path = fields[-1].strip()
        if path.startswith(_CURATION_QUEUE_PREFIX) and status == "D":
            active_deletions[path] = status
        elif path.startswith(_CURATION_ARCHIVE_PREFIX):
            archive_changes[path] = status
            if status == "A":
                archive_additions[path] = status

    expected_pairs = {
        active_path: _CURATION_ARCHIVE_PREFIX + active_path.rsplit("/", 1)[-1]
        for active_path in active_deletions
    }
    missing_archive = [
        archive_path
        for archive_path in expected_pairs.values()
        if archive_path not in archive_changes
    ]
    orphaned_archive_additions = [
        archive_path
        for archive_path in archive_additions
        if archive_path not in expected_pairs.values()
    ]
    transitions = [
        {
            "active_path": active_path,
            "archive_path": archive_path,
            "active_status": active_deletions[active_path],
            "archive_status": archive_changes[archive_path],
        }
        for active_path, archive_path in expected_pairs.items()
        if archive_path in archive_changes
    ]
    passed = not missing_archive and not orphaned_archive_additions
    return {
        "passed": passed,
        "status": "passed" if passed else "blocked",
        "checked_count": len(expected_pairs),
        "transitions": transitions,
        "missing_archive": missing_archive,
        "orphaned_archive_additions": orphaned_archive_additions,
        "recovery": (
            "Stage the exact active deletion and matching Archive path, then retry."
            if not passed else "Curation Queue Archive transitions are complete."
        ),
    }
