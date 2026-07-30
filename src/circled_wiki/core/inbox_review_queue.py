"""Minimal, exception-only human review work items for Inbox intake."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from .frontmatter import parse_markdown, render_markdown


REVIEW_ACTIONS = {
    "sensitivity_review_required": "complete_sensitivity_review",
    "pii_needs_review": "decide_safe_handling",
}


def _queue_root(knowledge_root: Path) -> Path:
    return knowledge_root.resolve().parent / "workspace" / "task" / "inbox-review-queue"


def _archive_root(knowledge_root: Path) -> Path:
    return knowledge_root.resolve().parent / "workspace" / "task" / ".archive" / "inbox-review-queue"


def _item_path(knowledge_root: Path, intake_id: str) -> Path:
    source_uuid = intake_id.rsplit("/", 1)[-1]
    try:
        canonical_uuid = str(UUID(source_uuid))
    except ValueError as error:
        raise ValueError("inbox review intake_id must contain a UUID") from error
    return _queue_root(knowledge_root) / f"{canonical_uuid}.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _requirements(data: Dict[str, object]) -> List[Dict[str, object]]:
    requirements = data.get("requirements")
    if not isinstance(requirements, list):
        return []
    return [dict(item) for item in requirements if isinstance(item, dict)]


def enqueue_inbox_review(
    knowledge_root: Path, *, intake_id: str, inbox_path: Path, source_checksum: str,
    current_stage: str, reason_code: str,
) -> Dict[str, object]:
    """Create or extend the one active review item for an exceptional Inbox item."""
    if reason_code not in REVIEW_ACTIONS:
        raise ValueError("inbox review reason_code is invalid")
    if not source_checksum.startswith("sha256:"):
        raise ValueError("inbox review source_checksum must be a sha256 checksum")
    knowledge_root = knowledge_root.resolve()
    path = _item_path(knowledge_root, intake_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    relative_inbox = inbox_path.resolve().relative_to(knowledge_root).as_posix()
    if path.is_file():
        data = parse_markdown(path).frontmatter
        if data.get("source_checksum") != source_checksum:
            raise ValueError("active inbox review belongs to a different source checksum")
        requirements = _requirements(data)
    else:
        data = {
            "type": "inbox_review_queue",
            "intake_id": intake_id,
            "inbox_path": relative_inbox,
            "source_checksum": source_checksum,
            "created_at": _now(),
        }
        requirements = []
    if not any(item.get("reason_code") == reason_code for item in requirements):
        requirements.append({
            "reason_code": reason_code,
            "requested_action": REVIEW_ACTIONS[reason_code],
            "status": "awaiting_user",
        })
    data.update({
        "current_stage": current_stage,
        "status": "awaiting_user",
        "requirements": requirements,
        "updated_at": _now(),
    })
    path.write_text(render_markdown(data), encoding="utf-8")
    return {"queue_id": path.stem, "queue_path": path, "status": "awaiting_user"}


def get_inbox_review(knowledge_root: Path, intake_id: str) -> Optional[Dict[str, object]]:
    path = _item_path(knowledge_root, intake_id)
    if not path.is_file():
        return None
    data = parse_markdown(path).frontmatter
    data["queue_id"] = path.stem
    data["queue_path"] = path
    return data


def has_blocking_inbox_review(knowledge_root: Path, intake_id: str, source_checksum: str) -> bool:
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return False
    if review.get("source_checksum") != source_checksum:
        raise ValueError("active inbox review belongs to a different source checksum")
    return review.get("status") == "awaiting_user"


def resolve_inbox_review_requirement(
    knowledge_root: Path, *, intake_id: str, source_checksum: str, reason_code: str,
    actor: str, decision: str, receipt: str,
) -> Dict[str, object]:
    """Record a decision, but retain the queue until Evidence creation succeeds."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return {"intake_id": intake_id, "reused": True, "status": "no_review"}
    if review.get("source_checksum") != source_checksum:
        raise ValueError("active inbox review belongs to a different source checksum")
    requirements = _requirements(review)
    matched = False
    for item in requirements:
        if item.get("reason_code") != reason_code:
            continue
        matched = True
        item.update({
            "status": "resolved", "decision": decision, "decided_by": actor,
            "decided_at": _now(), "receipt": receipt,
        })
    if not matched:
        return {"intake_id": intake_id, "reused": True, "status": str(review.get("status"))}
    review["requirements"] = requirements
    review["status"] = "reprocessing" if all(
        item.get("status") == "resolved" for item in requirements
    ) else "awaiting_user"
    review["updated_at"] = _now()
    path = review.pop("queue_path")
    review.pop("queue_id", None)
    path.write_text(render_markdown(review), encoding="utf-8")
    return {"intake_id": intake_id, "status": review["status"], "reused": False}


def review_context(knowledge_root: Path, intake_id: str, source_checksum: str) -> Optional[Dict[str, object]]:
    """Return safe resolved-review provenance for a newly created Evidence item."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None or review.get("source_checksum") != source_checksum:
        return None
    if review.get("status") != "reprocessing":
        return None
    return {
        "queue_id": str(review["queue_id"]),
        "reason_codes": [str(item["reason_code"]) for item in _requirements(review)],
        "decisions": [
            {
                "reason_code": str(item["reason_code"]),
                "decision": str(item["decision"]),
                "receipt": str(item["receipt"]),
            }
            for item in _requirements(review)
        ],
    }


def complete_inbox_review(
    knowledge_root: Path, *, intake_id: str, source_checksum: str, evidence_id: str,
) -> bool:
    """Archive a resolved review only after Evidence and its curation queue exist."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return False
    if review.get("source_checksum") != source_checksum or review.get("status") != "reprocessing":
        raise ValueError("inbox review is not ready to complete")
    source = review.pop("queue_path")
    review.pop("queue_id", None)
    review.update({"status": "resolved", "evidence_id": evidence_id, "resolved_at": _now()})
    archive = _archive_root(knowledge_root) / source.name
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(".tmp")
    temporary.write_text(render_markdown(review), encoding="utf-8")
    temporary.replace(archive)
    source.unlink(missing_ok=True)
    return True


def list_inbox_review_queue(knowledge_root: Path) -> List[Dict[str, object]]:
    root = _queue_root(knowledge_root)
    if not root.is_dir():
        return []
    items: List[Dict[str, object]] = []
    for path in sorted(root.glob("*.md")):
        try:
            data = parse_markdown(path).frontmatter
        except (OSError, ValueError):
            continue
        items.append({
            "queue_id": path.stem, "intake_id": data.get("intake_id"),
            "inbox_path": data.get("inbox_path"), "current_stage": data.get("current_stage"),
            "status": data.get("status"), "requirements": _requirements(data),
            "queue_path": path.relative_to(root.parent.parent.parent).as_posix(),
        })
    return items
