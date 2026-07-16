"""Git publication guarded by repository-wide validation."""

from pathlib import Path
import subprocess
from typing import Dict

from .validator import validate_repository
from .frontmatter import parse_markdown


class PublishError(RuntimeError):
    """A change was not safe or possible to publish."""


def publish_changes(project_root: Path, commit_message: str) -> Dict[str, object]:
    """Commit only `knowledge/` after all managed documents validate successfully."""
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
    _git(project_root, "add", "knowledge")
    staged_paths = _git(project_root, "diff", "--cached", "--name-only").stdout.splitlines()
    if any(not path.startswith("knowledge/") for path in staged_paths):
        raise PublishError("publication staging escaped the knowledge/ path boundary")
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
        if not isinstance(extensions, dict) or extensions.get("pii_scanned") is not True:
            raise PublishError(f"sensitive-data scan is incomplete: {manifest_path.relative_to(knowledge_root.parent)}")


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
