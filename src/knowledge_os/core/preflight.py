"""Read-only operational provenance checks for an installed Circled Wiki runtime."""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Set


MANIFEST_PATH = ".circled-wiki/manifest.json"
RUNTIME_PREFIX = ".circled-wiki/runtime/knowledge_os/"


def _checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_runtime_provenance(project_root: Path) -> Dict[str, object]:
    """Verify the executing runtime and installed Python assets against the manifest."""
    project = project_root.resolve()
    manifest_path = project / MANIFEST_PATH
    execution_path = Path(__file__).resolve()
    runtime_root = (project / ".circled-wiki" / "runtime" / "knowledge_os").resolve()
    source_tree = project / "src" / "knowledge_os"
    report: Dict[str, object] = {
        "release_id": None,
        "execution_module": str(execution_path),
        "canonical_runtime_root": str(runtime_root),
        "executing_canonical_runtime": _is_within(execution_path, runtime_root),
        "manifest_checksum": None,
        "manifest_valid": False,
        "runtime_asset_count": 0,
        "missing_assets": [],
        "mismatched_assets": [],
        "unexpected_assets": [],
        "source_tree_present": source_tree.is_dir(),
        "multiple_runtime_candidates": source_tree.is_dir() and runtime_root.is_dir(),
        "compatible": False,
    }
    if not manifest_path.is_file():
        return report
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return report
    assets = manifest.get("assets")
    release_id = manifest.get("os_release")
    if not isinstance(assets, dict) or not isinstance(release_id, str) or not release_id:
        return report
    runtime_assets = {
        path: checksum
        for path, checksum in assets.items()
        if isinstance(path, str)
        and path.startswith(RUNTIME_PREFIX)
        and path.endswith(".py")
        and isinstance(checksum, str)
    }
    expected_paths: Set[str] = set(runtime_assets)
    actual_paths: Set[str] = set()
    if runtime_root.is_dir():
        actual_paths = {
            f"{RUNTIME_PREFIX}{path.relative_to(runtime_root).as_posix()}"
            for path in runtime_root.rglob("*.py")
            if path.is_file()
        }
    missing: List[str] = []
    mismatched: List[str] = []
    for relative, expected_checksum in sorted(runtime_assets.items()):
        path = project / relative
        if not path.is_file():
            missing.append(relative)
        elif _checksum(path) != expected_checksum:
            mismatched.append(relative)
    unexpected = sorted(actual_paths - expected_paths)
    manifest_valid = bool(runtime_assets)
    compatible = bool(
        manifest_valid
        and report["executing_canonical_runtime"]
        and not missing
        and not mismatched
        and not unexpected
        and not report["multiple_runtime_candidates"]
    )
    report.update({
        "release_id": release_id,
        "manifest_checksum": _checksum(manifest_path),
        "manifest_valid": manifest_valid,
        "runtime_asset_count": len(runtime_assets),
        "missing_assets": missing,
        "mismatched_assets": mismatched,
        "unexpected_assets": unexpected,
        "compatible": compatible,
    })
    return report


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
