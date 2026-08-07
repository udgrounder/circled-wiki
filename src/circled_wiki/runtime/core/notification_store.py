"""Small file-backed, user-facing notification inbox for a Wiki workspace."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4


NOTIFICATION_EVENTS = {"bundle_created", "taxonomy_change_proposed", "reclassification_ready", "review_requested"}
NOTIFICATION_PRIORITIES = {"action_required", "attention", "failed"}


def record_user_notification(
    workspace_root: Path, *, event: str, priority: str, title: str, summary: str,
    next_action: str, resource_ref: str, approval_required: bool, dedupe_key: str,
    related_evidence_id: str = "", related_bundle_id: str = "", taxonomy_revision: str = "",
) -> Dict[str, object]:
    """Create one user-facing notification or reuse an open duplicate.

    The notification is a presentation projection only.  Source workflow state
    stays in its Curation, taxonomy, or reclassification record.
    """
    _validate_fields(event, priority, title, summary, next_action, resource_ref, approval_required, dedupe_key)
    for current in _notification_files(workspace_root / "notifications" / "inbox"):
        payload = _read_json(current)
        if payload.get("dedupe_key") == dedupe_key:
            return {**payload, "reused": True}
    notification_id = f"notification-{uuid4()}"
    payload: Dict[str, object] = {
        "schema_version": 1,
        "notification_id": notification_id,
        "event": event,
        "priority": priority,
        "title": title.strip(),
        "summary": summary.strip(),
        "next_action": next_action.strip(),
        "resource_ref": resource_ref.strip(),
        "approval_required": approval_required,
        "dedupe_key": dedupe_key.strip(),
        "created_at": _now(),
        "related_evidence_id": related_evidence_id.strip(),
        "related_bundle_id": related_bundle_id.strip(),
        "taxonomy_revision": taxonomy_revision.strip(),
    }
    _write_json(workspace_root / "notifications" / "inbox" / f"{notification_id}.json", payload)
    return {**payload, "reused": False}


def list_user_notifications(workspace_root: Path, *, include_acknowledged: bool = False) -> List[Dict[str, object]]:
    notifications_root = workspace_root / "notifications"
    records: List[Dict[str, object]] = []
    for path in _notification_files(notifications_root / "inbox"):
        payload = _read_json(path)
        notification_id = payload.get("notification_id")
        if not isinstance(notification_id, str):
            continue
        acknowledgement = _acknowledgement(notifications_root, notification_id)
        if acknowledgement is not None:
            payload["acknowledgement"] = acknowledgement
        if include_acknowledged or acknowledgement is None:
            records.append(payload)
    return records


def acknowledge_user_notification(workspace_root: Path, *, notification_id: str, actor: str) -> Dict[str, object]:
    if not notification_id.strip() or Path(notification_id).name != notification_id:
        raise ValueError("notification_id must be a safe non-empty identifier")
    if not actor.strip():
        raise ValueError("actor must be non-empty")
    notifications_root = workspace_root / "notifications"
    notification_path = notifications_root / "inbox" / f"{notification_id}.json"
    notification = _read_json(notification_path)
    if notification.get("notification_id") != notification_id:
        raise ValueError("notification_id must refer to a stored notification")
    existing = _acknowledgement(notifications_root, notification_id)
    if existing is not None:
        return {**existing, "reused": True}
    acknowledgement = {
        "schema_version": 1,
        "notification_id": notification_id,
        "action": "acknowledged",
        "actor": actor.strip(),
        "acknowledged_at": _now(),
    }
    _write_json(notifications_root / "acknowledgements" / f"{notification_id}.json", acknowledgement)
    return {**acknowledgement, "reused": False}


def require_acknowledged_user_notification(
    workspace_root: Path, *, notification_id: str, event: str,
) -> Dict[str, object]:
    """Return an acknowledged open notification of the required event type."""
    if event not in NOTIFICATION_EVENTS:
        raise ValueError("notification event is unsupported")
    if not notification_id.strip() or Path(notification_id).name != notification_id:
        raise ValueError("notification_id must be a safe non-empty identifier")
    notifications_root = workspace_root / "notifications"
    notification = _read_json(notifications_root / "inbox" / f"{notification_id}.json")
    if notification.get("notification_id") != notification_id or notification.get("event") != event:
        raise ValueError("notification_id must refer to the required open notification")
    if _acknowledgement(notifications_root, notification_id) is None:
        raise ValueError("notification must be acknowledged before this action")
    return notification


def archive_user_notification(workspace_root: Path, *, notification_id: str, reason: str) -> Dict[str, object]:
    if not notification_id.strip() or Path(notification_id).name != notification_id:
        raise ValueError("notification_id must be a safe non-empty identifier")
    if not reason.strip():
        raise ValueError("reason must be non-empty")
    notifications_root = workspace_root / "notifications"
    source = notifications_root / "inbox" / f"{notification_id}.json"
    payload = _read_json(source)
    payload["archived_at"] = _now()
    payload["archive_reason"] = reason.strip()
    destination = notifications_root / "archive" / source.name
    _write_json(destination, payload)
    source.unlink()
    return payload


def archive_notifications_for_resource(
    workspace_root: Path, *, resource_ref: str, reason: str,
) -> List[Dict[str, object]]:
    """Archive open presentation records when their source workflow resolves."""
    if not resource_ref.strip() or not reason.strip():
        raise ValueError("resource_ref and reason must be non-empty")
    archived: List[Dict[str, object]] = []
    inbox = workspace_root / "notifications" / "inbox"
    for path in _notification_files(inbox):
        payload = _read_json(path)
        if payload.get("resource_ref") != resource_ref:
            continue
        archived.append(archive_user_notification(
            workspace_root,
            notification_id=str(payload["notification_id"]),
            reason=reason,
        ))
    return archived


def _validate_fields(
    event: str, priority: str, title: str, summary: str, next_action: str,
    resource_ref: str, approval_required: bool, dedupe_key: str,
) -> None:
    if event not in NOTIFICATION_EVENTS:
        raise ValueError("notification event is unsupported")
    if priority not in NOTIFICATION_PRIORITIES:
        raise ValueError("notification priority is unsupported")
    if any(not value.strip() for value in (title, summary, next_action, resource_ref, dedupe_key)):
        raise ValueError("notification title, summary, next_action, resource_ref, and dedupe_key must be non-empty")
    if not isinstance(approval_required, bool):
        raise ValueError("notification approval_required must be boolean")


def _notification_files(directory: Path) -> List[Path]:
    return sorted(directory.glob("notification-*.json")) if directory.is_dir() else []


def _acknowledgement(notifications_root: Path, notification_id: str) -> Optional[Dict[str, object]]:
    path = notifications_root / "acknowledgements" / f"{notification_id}.json"
    return _read_json(path) if path.is_file() else None


def _read_json(path: Path) -> Dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"notification record is invalid: {path.name}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"notification record is invalid: {path.name}")
    return payload


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
