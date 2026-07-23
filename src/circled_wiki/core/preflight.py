"""Read-only operational provenance checks for an installed Circled Wiki runtime."""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Sequence, Set


MANIFEST_PATH = ".circled-wiki/manifest.json"
RUNTIME_PREFIX = ".circled-wiki/runtime/circled_wiki/"
PRODUCT_PROFILES = {"bootstrap-circled-wiki.md", "repository-engineering.md"}
CONTROL_PLANE_REFERENCES = {
    "AGENTS.md": (".circled-wiki/AGENT_ROUTER.md",),
    "CLAUDE.md": (".circled-wiki/AGENT_ROUTER.md",),
    "HERMES.md": (
        ".circled-wiki/AUTONOMOUS_AGENT_STARTUP.md",
        ".circled-wiki/AGENT_ROUTER.md",
    ),
    ".circled-wiki/AGENT_BOOTSTRAP.md": (
        ".circled-wiki/AGENT_ROUTER.md",
        ".circled-wiki/bin/circled-wiki.py",
    ),
    ".circled-wiki/AUTONOMOUS_AGENT_STARTUP.md": (
        ".circled-wiki/AGENT_ROUTER.md",
        ".circled-wiki/bin/circled-wiki.py",
    ),
}


def _checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_runtime_provenance(project_root: Path) -> Dict[str, object]:
    """Verify the executing runtime and installed Python assets against the manifest."""
    project = project_root.resolve()
    manifest_path = project / MANIFEST_PATH
    execution_path = Path(__file__).resolve()
    runtime_root = (project / ".circled-wiki" / "runtime" / "circled_wiki").resolve()
    source_tree = project / "src" / "circled_wiki"
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


def inspect_control_plane_readiness(
    project_root: Path, profiles: Sequence[str]
) -> Dict[str, object]:
    """Check unresolved upgrade proposals and executable operating references."""
    project = project_root.resolve()
    manifest_path = project / MANIFEST_PATH
    pending_proposals: List[Dict[str, str]] = []
    manifest_errors: List[str] = []
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest_errors.append("manifest is not readable JSON")
        else:
            raw_proposals = manifest.get("pending_proposals", [])
            if not isinstance(raw_proposals, list):
                manifest_errors.append("manifest pending_proposals must be a list")
            else:
                for item in raw_proposals:
                    if not isinstance(item, dict) or any(
                        not isinstance(item.get(field), str) or not item[field]
                        for field in ("path", "proposal", "checksum")
                    ):
                        manifest_errors.append(
                            "manifest contains an invalid pending proposal"
                        )
                        continue
                    pending_proposals.append({
                        "path": item["path"],
                        "proposal": item["proposal"],
                        "checksum": item["checksum"],
                    })

    missing_proposal_files = sorted(
        item["proposal"]
        for item in pending_proposals
        if not (project / item["proposal"]).is_file()
    )
    reference_errors: List[str] = []
    for relative, references in CONTROL_PLANE_REFERENCES.items():
        path = project / relative
        if not path.is_file():
            reference_errors.append(f"{relative}: file is missing")
            continue
        content = path.read_text(encoding="utf-8")
        for reference in references:
            if reference not in content:
                reference_errors.append(
                    f"{relative}: missing reference to {reference}"
                )

    router = project / ".circled-wiki" / "AGENT_ROUTER.md"
    if router.is_file():
        router_content = router.read_text(encoding="utf-8")
        for profile in profiles:
            reference = f"agent-rules/{profile}"
            if reference not in router_content:
                reference_errors.append(
                    f".circled-wiki/AGENT_ROUTER.md: missing reference to {reference}"
                )

    launcher = project / ".circled-wiki" / "bin" / "circled-wiki.py"
    launcher_executable = launcher.is_file() and os.access(launcher, os.X_OK)
    if launcher.is_file() and not launcher_executable:
        reference_errors.append(
            ".circled-wiki/bin/circled-wiki.py: launcher is not executable"
        )
    unexpected_profiles = sorted(set(profiles) & PRODUCT_PROFILES)
    compatible = not (
        pending_proposals
        or missing_proposal_files
        or reference_errors
        or unexpected_profiles
        or manifest_errors
    )
    return {
        "compatible": compatible,
        "pending_proposals": pending_proposals,
        "missing_proposal_files": missing_proposal_files,
        "reference_errors": reference_errors,
        "unexpected_profiles": unexpected_profiles,
        "launcher_executable": launcher_executable,
        "manifest_errors": manifest_errors,
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
