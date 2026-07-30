"""Minimal, rebuildable curation work items stored outside immutable Evidence."""

from contextlib import contextmanager
import fcntl
from pathlib import Path
import threading
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from .frontmatter import parse_markdown, render_markdown


_QUEUE_LOCKS: Dict[Path, threading.RLock] = {}
_QUEUE_LOCKS_GUARD = threading.Lock()


@contextmanager
def curation_queue_transaction(knowledge_root: Path):
    """Serialize queue reconciliation and terminal queue mutations across processes."""
    knowledge_root = knowledge_root.resolve()
    lock_path = knowledge_root.parent / ".runtime" / "locks" / "curation-queue.lock"
    with _QUEUE_LOCKS_GUARD:
        thread_lock = _QUEUE_LOCKS.setdefault(lock_path, threading.RLock())
    with thread_lock:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def enqueue_curation_work(knowledge_root: Path, evidence_id: str, evidence_path: Path) -> Path:
    """Atomically register one immutable Evidence record for later curation."""
    knowledge_root = knowledge_root.resolve()
    evidence_path = evidence_path.resolve()
    try:
        relative = evidence_path.relative_to(knowledge_root)
        evidence_path.relative_to(knowledge_root / "evidence")
    except ValueError as error:
        raise ValueError("curation queue path must refer to knowledge/evidence") from error
    if not evidence_id:
        raise ValueError("curation queue evidence_id must be non-empty")
    with curation_queue_transaction(knowledge_root):
        return _enqueue_curation_work_unlocked(
            knowledge_root, evidence_id, evidence_path, relative
        )


def _enqueue_curation_work_unlocked(
    knowledge_root: Path, evidence_id: str, evidence_path: Path,
    relative: Optional[Path] = None,
) -> Path:
    """Write one queue item while the caller holds the queue transaction lock."""
    if relative is None:
        relative = evidence_path.resolve().relative_to(knowledge_root.resolve())
    target = _item_path(knowledge_root, evidence_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"evidence_id": evidence_id, "evidence_path": relative.as_posix()}
    temporary = target.with_name(f".{target.name}.{uuid4()}.tmp")
    temporary.write_text(render_markdown(payload), encoding="utf-8")
    temporary.replace(target)
    return target


def complete_curation_work(knowledge_root: Path, evidence_id: str) -> bool:
    """Remove a work item only after a Bundle or Review card was created."""
    knowledge_root = knowledge_root.resolve()
    with curation_queue_transaction(knowledge_root):
        return _complete_curation_work_unlocked(knowledge_root, evidence_id)


def _complete_curation_work_unlocked(
    knowledge_root: Path, evidence_id: str
) -> bool:
    """Remove one queue item while the caller holds the queue transaction lock."""
    target = _item_path(knowledge_root, evidence_id)
    existed = target.exists()
    target.unlink(missing_ok=True)
    return existed


def record_curation_blocker(
    knowledge_root: Path, evidence_id: str, evidence_path: Path, *, reason: str,
    next_action: str,
) -> Path:
    """Annotate existing retryable work with an actionable, non-Evidence error."""
    if not reason.strip() or not next_action.strip():
        raise ValueError("reason and next_action must be non-empty")
    with curation_queue_transaction(knowledge_root):
        target = _enqueue_curation_work_unlocked(knowledge_root, evidence_id, evidence_path)
        data = parse_markdown(target).frontmatter
        data["last_blocker"] = {"reason": reason.strip(), "next_action": next_action.strip()}
        target.write_text(render_markdown(data), encoding="utf-8")
        return target


def list_curation_queue(knowledge_root: Path, *, include_resolved: bool = False) -> List[Dict[str, object]]:
    """List pending work-item files; file existence is the only queue status."""
    del include_resolved  # Compatibility: completed items no longer exist.
    knowledge_root = knowledge_root.resolve()
    root = _queue_root(knowledge_root)
    rows: List[Dict[str, object]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.md")):
        data = parse_markdown(path).frontmatter
        evidence_id = data.get("evidence_id")
        evidence_path = data.get("evidence_path")
        if not isinstance(evidence_id, str) or not isinstance(evidence_path, str):
            continue
        rows.append({
            "evidence_id": evidence_id,
            "path": evidence_path,
            "status": "pending",
            "queue_path": path.relative_to(knowledge_root.parent).as_posix(),
            **({"reason": data["last_blocker"].get("reason"), "next_action": data["last_blocker"].get("next_action")}
               if isinstance(data.get("last_blocker"), dict)
               and isinstance(data["last_blocker"].get("reason"), str)
               and isinstance(data["last_blocker"].get("next_action"), str)
               else {}),
        })
    return rows


def refresh_curation_queue(knowledge_root: Path) -> Dict[str, object]:
    """Repair pending work items by scanning immutable Evidence and outcomes."""
    knowledge_root = knowledge_root.resolve()
    with curation_queue_transaction(knowledge_root):
        return _refresh_curation_queue_unlocked(knowledge_root)


def _refresh_curation_queue_unlocked(
    knowledge_root: Path,
) -> Dict[str, object]:
    """Reconcile the full queue while holding its namespace transaction lock."""
    completed = _completed_evidence_ids(knowledge_root)
    expected: Dict[str, Path] = {}
    for path in sorted((knowledge_root / "evidence").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        data = parse_markdown(path).frontmatter
        evidence_id = data.get("id")
        if (
            data.get("type") == "evidence"
            and isinstance(evidence_id, str)
            and evidence_id not in completed
        ):
            expected[evidence_id] = path

    root = _queue_root(knowledge_root)
    existing_paths = set(root.glob("*.md")) if root.is_dir() else set()
    expected_paths = {_item_path(knowledge_root, evidence_id) for evidence_id in expected}
    created = 0
    repaired = 0
    removed = 0
    for evidence_id, path in expected.items():
        target = _item_path(knowledge_root, evidence_id)
        relative = path.relative_to(knowledge_root).as_posix()
        if not target.exists():
            _enqueue_curation_work_unlocked(
                knowledge_root, evidence_id, path, Path(relative)
            )
            created += 1
            continue
        try:
            data = parse_markdown(target).frontmatter
        except (OSError, ValueError):
            data = {}
        base = {"evidence_id": evidence_id, "evidence_path": relative}
        blocker = data.get("last_blocker") if isinstance(data, dict) else None
        valid_blocker = (
            isinstance(blocker, dict)
            and isinstance(blocker.get("reason"), str)
            and blocker["reason"].strip()
            and isinstance(blocker.get("next_action"), str)
            and blocker["next_action"].strip()
        )
        if not isinstance(data, dict) or any(data.get(key) != value for key, value in base.items()) or set(data) - {"evidence_id", "evidence_path", "last_blocker"}:
            _enqueue_curation_work_unlocked(
                knowledge_root, evidence_id, path, Path(relative)
            )
            repaired += 1
        elif blocker is not None and not valid_blocker:
            _enqueue_curation_work_unlocked(
                knowledge_root, evidence_id, path, Path(relative)
            )
            repaired += 1
    for path in existing_paths - expected_paths:
        path.unlink(missing_ok=True)
        removed += 1
    return {
        "path": root.relative_to(knowledge_root.parent).as_posix(),
        "pending_count": len(expected),
        "created_count": created,
        "repaired_count": repaired,
        "removed_count": removed,
    }


def _completed_evidence_ids(knowledge_root: Path) -> set[str]:
    from .validator import validate_document

    bundle_completed: set[str] = set()
    review_completed: set[str] = set()
    stale: set[str] = set()
    for path in sorted((knowledge_root / "bundles").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        if not validate_document(path, knowledge_root).is_valid:
            continue
        refs = parse_markdown(path).frontmatter.get("evidence")
        if isinstance(refs, list):
            bundle_completed.update(item for item in refs if isinstance(item, str))
    reviews = knowledge_root / "curation-reviews"
    if reviews.is_dir():
        for path in sorted(reviews.rglob("*.md")):
            if path.name in {"README.md", "index.md", "log.md"}:
                continue
            if not validate_document(path, knowledge_root).is_valid:
                continue
            review = parse_markdown(path).frontmatter
            refs = review.get("evidence_refs")
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, dict) and isinstance(ref.get("evidence_id"), str):
                        if review.get("status") == "stale":
                            stale.add(ref["evidence_id"])
                        else:
                            review_completed.add(ref["evidence_id"])
    return (bundle_completed - stale) | review_completed


def _queue_root(knowledge_root: Path) -> Path:
    return knowledge_root.parent / "workspace" / "task" / "curation-queue"


def _item_path(knowledge_root: Path, evidence_id: str) -> Path:
    source_uuid = Path(evidence_id).stem.rsplit("_", 1)[-1]
    try:
        canonical_uuid = str(UUID(source_uuid))
    except ValueError as error:
        raise ValueError("curation queue evidence_id must contain a source UUID") from error
    return _queue_root(knowledge_root) / f"{canonical_uuid}.md"
