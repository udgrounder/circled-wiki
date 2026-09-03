"""Reversible Inbox disposition for confidently non-business source material."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Dict, List

from .frontmatter import parse_markdown, render_markdown
from .ingest import iter_active_inbox_items, read_conversation_intake


def _pending_root(knowledge_root: Path) -> Path:
    return knowledge_root.parent / "workspace" / "inbox-disposals" / "pending"


def _find_inbox_item(knowledge_root: Path, intake_id: str) -> tuple[Path, Dict[str, object], object]:
    for path in iter_active_inbox_items(knowledge_root):
        data, content = read_conversation_intake(path)
        if data.get("id") == intake_id:
            return path, data, content
    raise ValueError("intake_id must refer to a pending Inbox item")


def quarantine_inbox_item(
    knowledge_root: Path, intake_id: str, *, classifier: str, rule_version: str,
    reason: str,
) -> Dict[str, object]:
    """Move a confidently non-business Inbox item into reversible quarantine.

    The classifier supplies its own policy decision; this common workflow never
    infers business relevance from source text.  Quarantined originals are not
    available to inspection, Evidence ingestion, or Curation.
    """
    if not all(isinstance(value, str) and value.strip() for value in (intake_id, classifier, rule_version, reason)):
        raise ValueError("intake_id, classifier, rule_version, and reason must be non-empty")
    knowledge_root = knowledge_root.resolve()
    path, data, content = _find_inbox_item(knowledge_root, intake_id)
    if data.get("status") not in {"pending", "needs_review"}:
        raise ValueError("only pending or needs_review Inbox items can be quarantined")
    from .inbox_review_queue import suspend_inbox_review

    source_checksum = str(data["checksum"])
    suspend_inbox_review(
        knowledge_root, intake_id=intake_id, actor=classifier,
    )
    provider = str(data["provider"])
    target_dir = knowledge_root / "inbox" / ".quarantine" / provider
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.exists():
        raise ValueError("quarantine target already exists")
    payload_path = content if isinstance(content, Path) else None
    moved_payload = None
    if payload_path is not None:
        moved_payload = target_dir / payload_path.name
        shutil.move(str(payload_path), str(moved_payload))
    shutil.move(str(path), str(target))
    record = {
        "type": "inbox_disposal", "intake_id": intake_id, "provider": provider,
        "source_checksum": source_checksum, "status": "pending_disposal_review",
        "classification": "non_business_confirmed",
        "classifier": classifier.strip(), "rule_version": rule_version.strip(),
        "reason": reason.strip(), "quarantined_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quarantine_path": target.relative_to(knowledge_root).as_posix(),
    }
    record_path = _pending_root(knowledge_root) / f"{intake_id.rsplit('/', 1)[-1]}.md"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(render_markdown(record), encoding="utf-8")
    return {"intake_id": intake_id, "status": record["status"], "record_path": record_path.relative_to(knowledge_root.parent).as_posix()}


def list_inbox_disposals(knowledge_root: Path) -> List[Dict[str, object]]:
    root = _pending_root(knowledge_root)
    if not root.is_dir():
        return []
    records = []
    for path in sorted(root.glob("*.md")):
        data = parse_markdown(path).frontmatter
        if data.get("type") == "inbox_disposal" and data.get("status") == "pending_disposal_review":
            records.append({**data, "record_path": path.relative_to(knowledge_root.parent).as_posix()})
    return records


def decide_inbox_disposal(knowledge_root: Path, intake_id: str, *, decision: str, actor: str) -> Dict[str, object]:
    """Recover a quarantined item or permanently dispose its original after review."""
    if decision not in {"recover", "dispose"} or not isinstance(actor, str) or not actor.strip():
        raise ValueError("decision must be recover or dispose and actor must be non-empty")
    record_path = _pending_root(knowledge_root) / f"{intake_id.rsplit('/', 1)[-1]}.md"
    if not record_path.is_file():
        raise ValueError("intake_id has no pending disposal review")
    record = dict(parse_markdown(record_path).frontmatter)
    if record.get("status") != "pending_disposal_review" or record.get("intake_id") != intake_id:
        raise ValueError("disposal record is invalid")
    knowledge_root = knowledge_root.resolve()
    quarantined = knowledge_root / str(record["quarantine_path"])
    if not quarantined.is_file():
        raise ValueError("quarantined Inbox original is unavailable")
    if decision == "recover":
        provider = str(record["provider"])
        destination = knowledge_root / "inbox" / provider / quarantined.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError("Inbox recovery target already exists")
        document = parse_markdown(quarantined)
        payload_name = document.frontmatter.get("payload_file")
        if isinstance(payload_name, str):
            payload = quarantined.parent / payload_name
            if payload.is_file():
                shutil.move(str(payload), str(destination.parent / payload.name))
        shutil.move(str(quarantined), str(destination))
        restored, _ = read_conversation_intake(destination)
        if restored.get("sensitivity_review") == "required":
            from .inbox_review_queue import enqueue_inbox_review

            enqueue_inbox_review(
                knowledge_root, intake_id=intake_id, inbox_path=destination,
                current_stage="sensitivity_review",
                reason_code="sensitivity_review_required",
            )
        outcome = "recovered"
    else:
        document = parse_markdown(quarantined)
        payload_name = document.frontmatter.get("payload_file")
        if isinstance(payload_name, str):
            (quarantined.parent / payload_name).unlink(missing_ok=True)
        quarantined.unlink()
        outcome = "disposed"
    record_path.unlink()
    return {"intake_id": intake_id, "status": outcome, "record_deleted": True}
