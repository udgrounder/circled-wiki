"""Derived, rebuildable work queue for Evidence that still needs curation."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .frontmatter import parse_markdown
from .repository import iter_documents


OPEN_STATUSES = {"pending", "review_pending", "needs_review"}


def list_curation_queue(knowledge_root: Path, *, include_resolved: bool = False) -> List[Dict[str, object]]:
    """Return queue rows derived from Evidence metadata, never from the queue file."""
    rows: List[Dict[str, object]] = []
    documents = [parse_markdown(path) for path in iter_documents(knowledge_root)]
    bundled_evidence = set()
    for document in documents:
        evidence_ids = document.frontmatter.get("evidence")
        if isinstance(evidence_ids, list):
            bundled_evidence.update(item for item in evidence_ids if isinstance(item, str))
    for document in documents:
        path = document.path
        data = document.frontmatter
        if data.get("type") != "evidence":
            continue
        extensions = data.get("extensions")
        if not isinstance(extensions, dict) or extensions.get("visibility") == "restricted":
            continue
        tracking = extensions.get("curation_queue")
        tracking = tracking if isinstance(tracking, dict) else {}
        status = _status(data, extensions, tracking, str(data.get("id")) in bundled_evidence)
        if not include_resolved and status not in OPEN_STATUSES:
            continue
        rows.append({
            "evidence_id": data.get("id"),
            "path": path.relative_to(knowledge_root.parent).as_posix(),
            "captured_at": data.get("captured_at"),
            "status": status,
            "review_id": tracking.get("review_id"),
            "updated_at": tracking.get("updated_at"),
        })
    return sorted(rows, key=lambda row: (str(row.get("captured_at") or ""), str(row.get("evidence_id") or "")))


def refresh_curation_queue(knowledge_root: Path) -> Dict[str, object]:
    """Regenerate the Workspace queue from all non-restricted Evidence records."""
    rows = list_curation_queue(knowledge_root)
    target = knowledge_root.parent / "workspace" / "task" / "curation-review-queue.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Curation Review Queue",
        "",
        "This derived queue lists Evidence that has not reached a curation conclusion. "
        "Regenerate it from Evidence metadata; do not edit it as the source of truth.",
        "",
        f"Generated at: {generated_at}",
        "",
        "| Status | Evidence ID | Review card | Captured at |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        review_id = str(row.get("review_id") or "")
        lines.append(
            f"| {row['status']} | `{row['evidence_id']}` | `{review_id}` | {row.get('captured_at') or ''} |"
        )
    if not rows:
        lines.append("| — | No pending Evidence | — | — |")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in sorted(OPEN_STATUSES)}
    return {"path": target.relative_to(knowledge_root.parent).as_posix(), "pending_count": len(rows), "counts": counts}


def _status(
    data: Dict[str, object], extensions: Dict[str, object], tracking: Dict[str, object], is_bundled: bool
) -> str:
    if is_bundled:
        return "bundled"
    status = tracking.get("status")
    if status in {"pending", "review_pending", "needs_review", "bundled", "no_bundle"}:
        return str(status)
    checksum = data.get("checksum")
    no_bundle = extensions.get("curation_no_bundle")
    if isinstance(no_bundle, dict) and no_bundle.get("evidence_checksum") == checksum:
        return "no_bundle"
    review = extensions.get("curation_review")
    if isinstance(review, dict):
        return "needs_review" if review.get("status") in {"needs_changes", "needs_review"} else "review_pending"
    attempt = extensions.get("curation_attempt")
    if isinstance(attempt, dict) and attempt.get("status") == "needs_review":
        return "needs_review"
    return "pending"
