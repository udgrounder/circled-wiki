"""Git publication guarded by repository-wide validation."""

from pathlib import Path
import subprocess
from typing import Dict, Tuple

from knowledge_os.config.settings import load_settings

from .validator import validate_repository
from .frontmatter import parse_markdown
from .pii import pii_scan_receipt_errors


class PublishError(RuntimeError):
    """A change was not safe or possible to publish."""


def publish_changes(project_root: Path, commit_message: str) -> Dict[str, object]:
    """Commit only configured safe paths after all managed documents validate."""
    allowed_paths = load_settings(project_root).publication.allowed_paths
    knowledge_root = project_root / "knowledge"
    results = validate_repository(knowledge_root)
    if not all(result.is_valid for result in results):
        raise PublishError("validation failed; automatic commit is blocked")
    _require_sensitive_data_review(knowledge_root)
    if not (project_root / ".git").exists():
        raise PublishError("project root is not a Git repository")
    preexisting_staged = _git(project_root, "diff", "--cached", "--name-only").stdout.splitlines()
    if preexisting_staged:
        raise PublishError("pre-existing staged changes must be cleared before knowledge publication")
    _git(project_root, "add", "--", *allowed_paths)
    staged_paths = _git(project_root, "diff", "--cached", "--name-only").stdout.splitlines()
    if any(not _is_allowed_path(path, allowed_paths) for path in staged_paths):
        raise PublishError("publication staging escaped the configured path boundary")
    staged = subprocess.run(
        ["git", "-C", str(project_root), "diff", "--cached", "--quiet"], check=False
    )
    if staged.returncode == 0:
        return {"committed": False, "reason": "no knowledge changes"}
    _git(project_root, "commit", "-m", commit_message)
    commit_hash = _git(project_root, "rev-parse", "HEAD").stdout.strip()
    return {"committed": True, "commit": commit_hash}


def _require_sensitive_data_review(knowledge_root: Path) -> None:
    """Do not commit a Git-tracked original until its security review is recorded."""
    for manifest_path in (knowledge_root / "evidence").rglob("*.md"):
        if manifest_path.name in {"index.md", "log.md"}:
            continue
        manifest = parse_markdown(manifest_path).frontmatter
        if manifest.get("type") != "evidence" or not manifest.get("original_file_git_tracked"):
            continue
        extensions = manifest.get("extensions", {})
        errors = pii_scan_receipt_errors(manifest)
        if not isinstance(extensions, dict) or extensions.get("pii_scanned") is not True:
            errors.insert(0, "extensions.pii_scanned must be true before publication")
        if errors:
            raise PublishError(
                "sensitive-data scan is incomplete or invalid: "
                f"{manifest_path.relative_to(knowledge_root.parent)}: {errors[0]}"
            )


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _is_allowed_path(path: str, allowed_paths: Tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(root + "/") for root in allowed_paths)
