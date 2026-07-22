"""Git publication guarded by repository-wide validation."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
from typing import Dict, Iterator, Tuple

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


def push_committed_changes(project_root: Path, commit: str) -> Dict[str, object]:
    """Push one already-created commit only through the configured remote/branch boundary."""
    settings = load_settings(project_root).publication
    if not settings.push_enabled:
        raise PublishError("publication push is disabled by configuration")
    if not isinstance(commit, str) or not commit.strip():
        raise PublishError("commit is required for push")
    if not (project_root / ".git").exists():
        raise PublishError("project root is not a Git repository")
    with _push_lock(project_root):
        current = _git(project_root, "rev-parse", "HEAD").stdout.strip()
        if current != commit.strip():
            raise PublishError("only the current HEAD commit may be pushed")
        branch = _git(project_root, "branch", "--show-current").stdout.strip()
        if branch != settings.push_branch:
            raise PublishError("current branch does not match the configured publication push branch")
        remotes = _git(project_root, "remote").stdout.splitlines()
        if settings.push_remote not in remotes:
            raise PublishError("configured publication push remote is unavailable")
        try:
            _git(project_root, "push", settings.push_remote, f"HEAD:refs/heads/{settings.push_branch}")
        except subprocess.CalledProcessError as error:
            receipt = _record_push_receipt(
                project_root, current, settings.push_remote, settings.push_branch,
                status="commit_pending_push",
            )
            raise PublishError(
                "push failed; commit_pending_push receipt recorded at " + receipt["path"]
            ) from error
        receipt = _record_push_receipt(
            project_root, current, settings.push_remote, settings.push_branch, status="pushed",
        )
    return {
        "pushed": True, "commit": current, "remote": settings.push_remote,
        "branch": settings.push_branch, "receipt": receipt,
    }


@contextmanager
def _push_lock(project_root: Path) -> Iterator[None]:
    """Serialize push attempts without placing a lock file in Git-tracked knowledge."""
    lock_path = project_root / ".runtime" / "locks" / "publication-push.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PublishError("another publication push is already running") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _record_push_receipt(
    project_root: Path, commit: str, remote: str, branch: str, *, status: str,
) -> Dict[str, object]:
    """Persist retry-safe local push state without recording remote credentials or output."""
    directory = project_root / ".runtime" / "publication" / "push"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{commit}.json"
    prior: Dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prior = loaded
        except (OSError, ValueError):
            prior = {}
    attempts = int(prior.get("attempts", 0)) + 1
    payload = {
        "commit": commit,
        "remote": remote,
        "branch": branch,
        "status": status,
        "attempts": attempts,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**payload, "path": path.relative_to(project_root).as_posix()}


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
