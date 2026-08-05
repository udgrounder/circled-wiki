"""Contract-scoped, rebuildable Curation task records outside immutable Evidence."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from pathlib import Path
import threading
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from .frontmatter import parse_markdown, render_markdown


_QUEUE_LOCKS: Dict[Path, threading.RLock] = {}
_QUEUE_LOCKS_GUARD = threading.Lock()
CONTRACT_NAME = "curation_reconciliation"
CONTRACT_VERSION = 1


@contextmanager
def curation_queue_transaction(knowledge_root: Path):
    """Serialize queue reconciliation and terminal queue mutations across processes."""
    knowledge_root = knowledge_root.resolve()
    lock_path = knowledge_root.parent / ".runtime" / "locks" / "curation-reconciliation.lock"
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
    payload: Dict[str, object]
    if target.is_file():
        payload = parse_markdown(target).frontmatter
    else:
        archived = _archive_path(knowledge_root, evidence_id)
        if archived.is_file():
            payload = parse_markdown(archived).frontmatter
            archived.unlink()
        else:
            payload = {}
    if payload and payload.get("evidence_id") not in {None, evidence_id}:
        # The task filename is derived from the canonical UUID.  A mismatched
        # payload is corrupted state, so refresh replaces it with the current
        # immutable Evidence binding instead of trusting the stale contents.
        payload = {}
    previous = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    current = {
        "stage": "queued",
        "status": "pending",
        "actor": "curation-agent",
        "next_action": "run_configured_curation_batch",
    }
    payload.update({
        "type": "contract_task",
        "contract": {"name": CONTRACT_NAME, "version": CONTRACT_VERSION},
        "evidence_id": evidence_id,
        "evidence_path": relative.as_posix(),
        "current": current,
    })
    if previous.get("status") != "pending":
        _append_transition(payload, from_current=previous or None, to_current=current, outcome="queued")
        _append_step(payload, stage="queued", status="pending", outcome="queued")
    _write_task(target, payload)
    return target


def complete_curation_work(knowledge_root: Path, evidence_id: str) -> bool:
    """Close the active task only after an actual result artifact was created."""
    knowledge_root = knowledge_root.resolve()
    with curation_queue_transaction(knowledge_root):
        return _complete_curation_work_unlocked(knowledge_root, evidence_id)


def rollback_curation_work(knowledge_root: Path, evidence_id: str) -> bool:
    """Remove a newly-created pending Queue item during Inbox ingest rollback."""
    knowledge_root = knowledge_root.resolve()
    with curation_queue_transaction(knowledge_root):
        target = _item_path(knowledge_root, evidence_id)
        if not target.is_file():
            return False
        target.unlink(missing_ok=True)
        return True


def _complete_curation_work_unlocked(
    knowledge_root: Path, evidence_id: str
) -> bool:
    """Remove one queue item while the caller holds the queue transaction lock."""
    target = _item_path(knowledge_root, evidence_id)
    if not target.is_file():
        return False
    payload = parse_markdown(target).frontmatter
    previous = payload.get("current") if isinstance(payload.get("current"), dict) else None
    payload["current"] = {
        "stage": "result_created", "status": "completed", "actor": "curation-agent",
    }
    payload.pop("last_blocker", None)
    _append_step(payload, stage="result_created", status="completed")
    _append_transition(
        payload, from_current=previous, to_current=payload["current"], outcome="result_created",
    )
    archive = _archive_path(knowledge_root, evidence_id)
    _write_task(archive, payload)
    target.unlink(missing_ok=True)
    return True


def record_curation_contract_outcome(
    knowledge_root: Path, evidence_id: str, *, outcome: str, next_stage: str,
    artifact: Optional[Dict[str, object]] = None,
) -> bool:
    """Record a contract outcome only after its referenced result exists.

    This updates the contract task record; it never creates a Bundle, Review
    card, or no-bundle decision. Those artifacts are produced by Curation first.
    """
    knowledge_root = knowledge_root.resolve()
    with curation_queue_transaction(knowledge_root):
        target = _archive_path(knowledge_root, evidence_id)
        if not target.is_file():
            return False
        payload = parse_markdown(target).frontmatter
        previous = payload.get("current") if isinstance(payload.get("current"), dict) else None
        payload["current"] = {
            "stage": next_stage,
            "status": "completed",
            "actor": "curation-agent",
            "outcome": outcome,
        }
        if artifact:
            payload["result_artifact"] = artifact
        _append_step(payload, stage=next_stage, status="completed", outcome=outcome)
        _append_transition(
            payload, from_current=previous, to_current=payload["current"], outcome=outcome,
        )
        _write_task(target, payload)
        return True


def record_curation_blocker(
    knowledge_root: Path, evidence_id: str, evidence_path: Path, *, reason: str,
    reason_category: str, next_action: str,
) -> Path:
    """Annotate existing retryable work with an actionable, non-Evidence error."""
    if not reason.strip() or not reason_category.strip() or not next_action.strip():
        raise ValueError("reason, reason_category, and next_action must be non-empty")
    with curation_queue_transaction(knowledge_root):
        target = _enqueue_curation_work_unlocked(knowledge_root, evidence_id, evidence_path)
        data = parse_markdown(target).frontmatter
        data["last_blocker"] = {
            "reason": reason.strip(), "reason_category": reason_category.strip(),
            "next_action": next_action.strip(),
        }
        previous = data.get("current") if isinstance(data.get("current"), dict) else None
        data["current"] = {
            "stage": "queued", "status": "pending", "actor": "curation-agent",
            "next_action": next_action.strip(),
        }
        _append_step(data, stage="queued", status="pending", outcome="retryable_block", reason=reason.strip())
        _append_transition(
            data, from_current=previous, to_current=data["current"], outcome="retryable_block",
        )
        _write_task(target, data)
        return target


def list_curation_queue(knowledge_root: Path, *, include_resolved: bool = False) -> List[Dict[str, object]]:
    """List pending Curation contract tasks; the Queue is a derived view."""
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
        current = data.get("current")
        if not isinstance(current, dict) or current.get("status") != "pending":
            continue
        rows.append({
            "evidence_id": evidence_id,
            "path": evidence_path,
            "status": "pending",
            "queue_path": path.relative_to(knowledge_root.parent).as_posix(),
            **({
                "reason": data["last_blocker"].get("reason"),
                "reason_category": data["last_blocker"].get("reason_category"),
                "next_action": data["last_blocker"].get("next_action"),
            }
               if isinstance(data.get("last_blocker"), dict)
               and isinstance(data["last_blocker"].get("reason"), str)
               and isinstance(data["last_blocker"].get("reason_category"), str)
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
            and isinstance(blocker.get("reason_category"), str)
            and blocker["reason_category"].strip()
            and isinstance(blocker.get("next_action"), str)
            and blocker["next_action"].strip()
        )
        if not isinstance(data, dict) or any(data.get(key) != value for key, value in base.items()) or not _valid_task_record(data):
            _enqueue_curation_work_unlocked(
                knowledge_root, evidence_id, path, Path(relative)
            )
            repaired += 1
        elif blocker is not None and not valid_blocker:
            # A malformed blocker must not survive a reported repair.  Preserve
            # the task receipts, but discard only the unusable diagnostic data
            # and return the task to the contract's normal queued action.
            data.pop("last_blocker", None)
            previous = data.get("current") if isinstance(data.get("current"), dict) else None
            data["current"] = {
                "stage": "queued",
                "status": "pending",
                "actor": "curation-agent",
                "next_action": "run_configured_curation_batch",
            }
            _append_step(data, stage="queued", status="pending", outcome="blocker_repaired")
            _append_transition(
                data, from_current=previous, to_current=data["current"], outcome="blocker_repaired",
            )
            _write_task(target, data)
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
    return knowledge_root.parent / "workspace" / "task" / CONTRACT_NAME


def _archive_root(knowledge_root: Path) -> Path:
    return knowledge_root.parent / "workspace" / "task" / ".archive" / CONTRACT_NAME


def _archive_path(knowledge_root: Path, evidence_id: str) -> Path:
    return _archive_root(knowledge_root) / _item_path(knowledge_root, evidence_id).name


def _append_step(
    payload: Dict[str, object], *, stage: str, status: str, outcome: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    steps = payload.get("step_receipts")
    if not isinstance(steps, list):
        steps = []
    receipt: Dict[str, object] = {
        "stage": stage,
        "status": status,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if outcome is not None:
        receipt["outcome"] = outcome
    if reason is not None:
        receipt["reason"] = reason
    steps.append(receipt)
    payload["step_receipts"] = steps


def _append_transition(
    payload: Dict[str, object], *, from_current: Optional[Dict[str, object]],
    to_current: Dict[str, object], outcome: str,
) -> None:
    transitions = payload.get("transitions")
    if not isinstance(transitions, list):
        transitions = []
    transitions.append({
        "from": from_current,
        "to": dict(to_current),
        "outcome": outcome,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    payload["transitions"] = transitions


def _write_task(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    temporary.write_text(render_markdown(payload), encoding="utf-8")
    temporary.replace(path)


def _valid_task_record(data: Dict[str, object]) -> bool:
    contract = data.get("contract")
    current = data.get("current")
    return (
        data.get("type") == "contract_task"
        and isinstance(contract, dict)
        and contract == {"name": CONTRACT_NAME, "version": CONTRACT_VERSION}
        and isinstance(current, dict)
        and current.get("stage") == "queued"
        and current.get("status") == "pending"
        and isinstance(current.get("actor"), str)
        and isinstance(data.get("step_receipts"), list)
        and isinstance(data.get("transitions"), list)
    )


def _item_path(knowledge_root: Path, evidence_id: str) -> Path:
    source_uuid = Path(evidence_id).stem.rsplit("_", 1)[-1]
    try:
        canonical_uuid = str(UUID(source_uuid))
    except ValueError as error:
        raise ValueError("curation queue evidence_id must contain a source UUID") from error
    return _queue_root(knowledge_root) / f"{canonical_uuid}.md"
