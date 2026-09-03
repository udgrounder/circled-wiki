"""Contract work records for Inbox intake and exceptional user review."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from .frontmatter import parse_markdown, render_markdown
from .inbox_contracts import SUPPORTED_INBOX_REVIEW_REQUIREMENTS
from .pii import pii_scan_receipt_errors
from .data_protection_receipt import (
    data_protection_candidate_checksum,
    data_protection_receipt_errors,
)


REVIEW_ACTIONS = {
    reason: str(requirement["requested_action"])
    for reason, requirement in SUPPORTED_INBOX_REVIEW_REQUIREMENTS.items()
}
USER_ONLY_REQUIREMENTS = {"pii_needs_review"}
CONTRACT_NAME = "inbox_reconciliation"
CONTRACT_VERSION = 1


def _queue_root(knowledge_root: Path) -> Path:
    return knowledge_root.resolve().parent / "workspace" / "task" / CONTRACT_NAME


def _item_path(knowledge_root: Path, intake_id: str) -> Path:
    source_uuid = intake_id.rsplit("/", 1)[-1]
    try:
        canonical_uuid = str(UUID(source_uuid))
    except ValueError as error:
        raise ValueError("inbox review intake_id must contain a UUID") from error
    return _queue_root(knowledge_root) / f"{canonical_uuid}.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _candidate_for_receipt(path: Path, data: Dict[str, object]) -> object:
    """Read only the current candidate needed to bind the Data Protection Receipt."""
    document = parse_markdown(path)
    if data.get("content_type") == "file":
        payload_name = data.get("payload_file")
        if not isinstance(payload_name, str) or Path(payload_name).name != payload_name:
            raise ValueError("Inbox file payload_file is invalid")
        payload = path.parent / payload_name
        if not payload.is_file():
            raise ValueError("Inbox file payload is missing")
        return payload
    start = document.body.find("<!-- INBOX_CONTENT_START -->")
    end = document.body.find("<!-- INBOX_CONTENT_END -->", start + len("<!-- INBOX_CONTENT_START -->"))
    if start < 0 or end < 0:
        raise ValueError("Inbox item content markers are missing")
    return document.body[start + len("<!-- INBOX_CONTENT_START -->"):end]


def _requirements(data: Dict[str, object]) -> List[Dict[str, object]]:
    requirements = data.get("requirements")
    if not isinstance(requirements, list):
        return []
    return [dict(item) for item in requirements if isinstance(item, dict)]


def _validate_requirement_pii_receipts(data: Dict[str, object]) -> None:
    """Reject a persisted user-decision request with an invalid PII receipt."""
    for requirement in _requirements(data):
        receipt = requirement.get("pii_scan")
        if receipt is None:
            continue
        if not isinstance(receipt, dict):
            raise ValueError("Inbox task requirement pii_scan must be an object")
        categories = receipt.get("categories")
        if not isinstance(categories, list) or any(
            not isinstance(category, str) or not category.strip() for category in categories
        ):
            raise ValueError("Inbox task requirement pii_scan categories are invalid")
        result = receipt.get("result")
        probe = {
            "checksum": receipt.get("source_checksum"),
            "extensions": {
                "pii_scan": receipt,
                "pii_scanned": result in {"passed", "masked"},
                "pii_masked": result == "masked",
            },
        }
        errors = pii_scan_receipt_errors(probe)
        if errors:
            raise ValueError("Inbox task requirement PII receipt is invalid: " + "; ".join(errors))


def _append_transition(
    data: Dict[str, object], *, from_current: Optional[Dict[str, object]],
    to_current: Dict[str, object], outcome: str,
) -> None:
    transitions = data.get("transitions")
    if not isinstance(transitions, list):
        transitions = []
    transitions.append({
        "from": from_current,
        "to": dict(to_current),
        "outcome": outcome,
        "recorded_at": _now(),
    })
    data["transitions"] = transitions


def ensure_inbox_task(
    knowledge_root: Path, *, intake_id: str, inbox_path: Path,
) -> Dict[str, object]:
    """Create the one Inbox contract task; normal work is not a review item."""
    knowledge_root = knowledge_root.resolve()
    path = _item_path(knowledge_root, intake_id)
    relative_inbox = inbox_path.resolve().relative_to(knowledge_root).as_posix()
    if path.is_file():
        return {"queue_id": path.stem, "queue_path": path, "reused": True}
    path.parent.mkdir(parents=True, exist_ok=True)
    current = {
        "stage": "pending", "status": "pending",
        "actor": "inbox-inspection-agent", "next_action": "accept_ready_inbox",
    }
    data: Dict[str, object] = {
        "type": "contract_task",
        "contract": {"name": CONTRACT_NAME, "version": CONTRACT_VERSION},
        "subject": {"intake_id": intake_id, "inbox_path": relative_inbox},
        "intake_id": intake_id,
        "inbox_path": relative_inbox,
        "requirements": [],
        "created_at": _now(),
        "updated_at": _now(),
        "current": current,
    }
    _append_transition(data, from_current=None, to_current=current, outcome="captured")
    _append_step(data, stage="pending", status="pending", outcome="captured")
    path.write_text(render_markdown(data), encoding="utf-8")
    return {"queue_id": path.stem, "queue_path": path, "reused": False}


def enqueue_inbox_review(
    knowledge_root: Path, *, intake_id: str, inbox_path: Path,
    current_stage: str, reason_code: str,
) -> Dict[str, object]:
    """Add a user-only requirement to the Inbox contract task."""
    requirement = SUPPORTED_INBOX_REVIEW_REQUIREMENTS.get(reason_code)
    if requirement is None:
        raise ValueError("inbox review reason_code is invalid")
    if current_stage != requirement["current_stage"]:
        raise ValueError("inbox review current_stage is invalid for its reason_code")
    knowledge_root = knowledge_root.resolve()
    task = ensure_inbox_task(
        knowledge_root, intake_id=intake_id, inbox_path=inbox_path,
    )
    path = task["queue_path"]
    relative_inbox = inbox_path.resolve().relative_to(knowledge_root).as_posix()
    if path.is_file():
        data = parse_markdown(path).frontmatter
        data.pop("source_checksum", None)
        data.update({
            "type": "contract_task",
            "contract": {"name": CONTRACT_NAME, "version": CONTRACT_VERSION},
            "subject": {
                "intake_id": intake_id,
                "inbox_path": relative_inbox,
            },
            "intake_id": intake_id,
            "inbox_path": relative_inbox,
        })
        requirements = _requirements(data)
    awaiting_user = reason_code in USER_ONLY_REQUIREMENTS
    requirement_status = "awaiting_user" if awaiting_user else "pending"
    if not any(item.get("reason_code") == reason_code for item in requirements):
        requirements.append({
            "reason_code": reason_code,
            "requested_action": requirement["requested_action"],
            "status": requirement_status,
        })
    status = requirement_status
    previous = data.get("current") if isinstance(data.get("current"), dict) else None
    current = {
        "stage": current_stage, "status": status,
        "actor": "user" if awaiting_user else "inbox-inspection-agent",
        "next_action": requirement["requested_action"],
    }
    data.update({
        "requirements": requirements,
        "updated_at": _now(),
        "current": current,
    })
    _append_transition(data, from_current=previous, to_current=current, outcome=reason_code)
    _append_step(data, stage=current_stage, status=status, outcome=reason_code)
    path.write_text(render_markdown(data), encoding="utf-8")
    return {"queue_id": path.stem, "queue_path": path, "status": status}


def get_inbox_review(knowledge_root: Path, intake_id: str) -> Optional[Dict[str, object]]:
    path = _item_path(knowledge_root, intake_id)
    if not path.is_file():
        return None
    data = parse_markdown(path).frontmatter
    _validate_requirement_pii_receipts(data)
    data["queue_id"] = path.stem
    data["queue_path"] = path
    return data


def reconcile_orphaned_inbox_reviews(knowledge_root: Path, *, actor: str) -> List[Dict[str, object]]:
    """Discard review tasks whose referenced Inbox source no longer exists."""
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    knowledge_root = knowledge_root.resolve()
    removed: List[Dict[str, object]] = []
    for path in sorted(_queue_root(knowledge_root).glob("*.md")):
        data = parse_markdown(path).frontmatter
        relative = data.get("inbox_path")
        if not isinstance(relative, str) or not relative.strip():
            continue
        inbox_path = (knowledge_root / relative).resolve()
        if knowledge_root not in inbox_path.parents or inbox_path.is_file():
            continue
        path.unlink(missing_ok=True)
        removed.append({"intake_id": str(data.get("intake_id", "")), "deleted": True})
    return removed


def has_blocking_inbox_review(knowledge_root: Path, intake_id: str) -> bool:
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return False
    current = review.get("current")
    return isinstance(current, dict) and current.get("status") == "awaiting_user"


def inbox_review_is_resolved(knowledge_root: Path, intake_id: str) -> bool:
    """Return whether every recorded Inbox requirement has been resolved."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return False
    requirements = _requirements(review)
    return bool(requirements) and all(item.get("status") == "resolved" for item in requirements)


def escalate_inbox_sensitivity_review(
    knowledge_root: Path, *, intake_id: str, actor: str, question: str,
    missing_procedure: str, safe_next_action: str, facts: List[str],
    hypotheses: List[str], pii_scan_receipt: Dict[str, object],
) -> Dict[str, object]:
    """Move an unresolved sensitivity inspection to a structured user decision."""
    required_text = {
        "actor": actor, "question": question, "missing_procedure": missing_procedure,
        "safe_next_action": safe_next_action,
    }
    if any(not isinstance(value, str) or not value.strip() for value in required_text.values()):
        raise ValueError("sensitivity escalation fields must be non-empty strings")
    for name, values in {"facts": facts, "hypotheses": hypotheses}.items():
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise ValueError(f"{name} must be a list of non-empty strings")
    if not isinstance(pii_scan_receipt, dict):
        raise ValueError("pii_scan_receipt must be an object")
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        raise ValueError("Inbox contract task is missing")
    requirements = _requirements(review)
    requirement = next(
        (item for item in requirements if item.get("reason_code") == "sensitivity_review_required"),
        None,
    )
    if requirement is None:
        raise ValueError("sensitivity review is not required")
    if requirement.get("status") == "resolved":
        raise ValueError("sensitivity review is already resolved")
    requirement.update({
        "status": "awaiting_user",
        "question": question.strip(),
        "blocked_step": "sensitivity_review",
        "missing_procedure": missing_procedure.strip(),
        "safe_next_action": safe_next_action.strip(),
        "facts": [value.strip() for value in facts],
        "hypotheses": [value.strip() for value in hypotheses],
        "pii_scan": dict(pii_scan_receipt),
        "escalated_by": actor.strip(),
        "escalated_at": _now(),
    })
    previous = review.get("current") if isinstance(review.get("current"), dict) else None
    current = {
        "stage": "sensitivity_review", "status": "awaiting_user", "actor": "user",
        "next_action": safe_next_action.strip(),
    }
    review.update({"requirements": requirements, "updated_at": _now(), "current": current})
    _append_transition(
        review, from_current=previous, to_current=current, outcome="sensitivity_user_decision_required",
    )
    _append_step(
        review, stage="sensitivity_review", status="awaiting_user",
        outcome="sensitivity_user_decision_required",
    )
    path = review.pop("queue_path")
    review.pop("queue_id", None)
    path.write_text(render_markdown(review), encoding="utf-8")
    return {"intake_id": intake_id, "status": "awaiting_user", "reused": False}


def resolve_inbox_review_requirement(
    knowledge_root: Path, *, intake_id: str, reason_code: str,
    actor: str, decision: str, receipt: str,
) -> Dict[str, object]:
    """Record a decision, but retain the queue until Evidence creation succeeds."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return {"intake_id": intake_id, "reused": True, "status": "no_review"}
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
        current = review.get("current")
        status = current.get("status") if isinstance(current, dict) else "unknown"
        return {"intake_id": intake_id, "reused": True, "status": str(status)}
    review["requirements"] = requirements
    status = "reprocessing" if all(
        item.get("status") == "resolved" for item in requirements
    ) else "awaiting_user"
    review["updated_at"] = _now()
    previous = review.get("current") if isinstance(review.get("current"), dict) else None
    review["current"] = {
        "stage": str(previous.get("stage", "inbox_review")) if previous else "inbox_review",
        "status": status,
        "actor": actor,
        "next_action": (
            SUPPORTED_INBOX_REVIEW_REQUIREMENTS[reason_code]["resolved_next_action"]
            if status == "reprocessing" else REVIEW_ACTIONS[reason_code]
        ),
    }
    _append_transition(
        review, from_current=previous, to_current=review["current"], outcome=decision,
    )
    _append_step(
        review, stage=str(review["current"]["stage"]), status=status, outcome=decision,
    )
    path = review.pop("queue_path")
    review.pop("queue_id", None)
    path.write_text(render_markdown(review), encoding="utf-8")
    return {"intake_id": intake_id, "status": status, "reused": False}


def reopen_inbox_data_protection_review(
    knowledge_root: Path, *, intake_id: str, actor: str,
) -> Dict[str, object]:
    """Expire prior Data Protection decisions after the Inbox candidate changes."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return {"intake_id": intake_id, "reused": True, "status": "no_review"}
    requirements = _requirements(review)
    changed = False
    for item in requirements:
        if item.get("reason_code") not in {
            "sensitivity_review_required", "data_protection_required",
            "pii_scan_required", "pii_needs_review",
        }:
            continue
        if item.get("status") == "resolved":
            changed = True
        item["status"] = "pending"
        for field in (
            "decision", "decided_by", "decided_at", "receipt", "question",
            "blocked_step", "missing_procedure", "safe_next_action", "facts",
            "hypotheses", "pii_scan", "escalated_by", "escalated_at",
        ):
            item.pop(field, None)
    if not changed:
        return {"intake_id": intake_id, "reused": True, "status": str(review.get("current", {}).get("status", "pending"))}
    previous = review.get("current") if isinstance(review.get("current"), dict) else None
    current = {
        "stage": "sensitivity_review", "status": "pending", "actor": actor,
        "next_action": "review_data_protection",
    }
    review.update({"requirements": requirements, "updated_at": _now(), "current": current})
    _append_transition(review, from_current=previous, to_current=current, outcome="data_protection_expired")
    _append_step(review, stage="sensitivity_review", status="pending", outcome="data_protection_expired")
    path = review.pop("queue_path")
    review.pop("queue_id", None)
    path.write_text(render_markdown(review), encoding="utf-8")
    return {"intake_id": intake_id, "reused": False, "status": "pending"}


def review_context(knowledge_root: Path, intake_id: str) -> Optional[Dict[str, object]]:
    """Return safe resolved-review provenance for a newly created Evidence item."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return None
    requirements = _requirements(review)
    if not requirements or not all(item.get("status") == "resolved" for item in requirements):
        return None
    inbox_path = knowledge_root.resolve() / str(review.get("inbox_path", ""))
    try:
        inbox = parse_markdown(inbox_path).frontmatter
    except (OSError, ValueError):
        return None
    receipt = inbox.get("data_protection_receipt")
    errors = data_protection_receipt_errors(
        receipt, checksum=str(inbox.get("checksum", "")),
        candidate_checksum=data_protection_candidate_checksum(
            inbox, _candidate_for_receipt(inbox_path, inbox)
        ),
        require_resolved=True,
    )
    if errors:
        return None
    return {
        "queue_id": str(review["queue_id"]),
        "reason_codes": [str(item["reason_code"]) for item in requirements],
        "decisions": [
            {
                "reason_code": str(item["reason_code"]),
                "decision": str(item["decision"]),
                "receipt": str(item["receipt"]),
            }
            for item in requirements
        ],
        "data_protection_receipt": dict(receipt),
    }


def complete_inbox_review(
    knowledge_root: Path, *, intake_id: str, evidence_id: str,
) -> bool:
    """Delete the completed Inbox task after its provenance reached Evidence."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return False
    if not inbox_review_is_resolved(knowledge_root, intake_id):
        raise ValueError("inbox task has unresolved requirements")
    # ``review_context`` is copied into the immutable Evidence manifest before
    # this function is reached.  Keeping a completed task would duplicate the
    # same decisions and data-protection receipt.
    del evidence_id
    review["queue_path"].unlink(missing_ok=True)
    return True


def reopen_inbox_review_after_ingest_failure(
    knowledge_root: Path, *, intake_id: str, reason: str,
) -> bool:
    """Return an active Inbox contract task to retryable accepted state."""
    knowledge_root = knowledge_root.resolve()
    active = _item_path(knowledge_root, intake_id)
    if not active.is_file():
        return False
    payload = parse_markdown(active).frontmatter
    previous = payload.get("current") if isinstance(payload.get("current"), dict) else None
    payload.pop("evidence_id", None)
    payload.pop("resolved_at", None)
    payload["current"] = {
        "stage": "accepted", "status": "pending", "actor": "evidence-ingest-agent",
        "next_action": "retry_evidence_ingest",
    }
    _append_transition(
        payload, from_current=previous, to_current=payload["current"],
        outcome="evidence_ingest_retry",
    )
    _append_step(
        payload, stage="accepted", status="pending", outcome="evidence_ingest_retry",
        reason=reason,
    )
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text(render_markdown(payload), encoding="utf-8")
    return True


def advance_inbox_task(
    knowledge_root: Path, *, intake_id: str, stage: str, status: str,
    actor: str, next_action: str, outcome: str,
) -> bool:
    """Record an Agent-owned Inbox contract transition without changing its source."""
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return False
    if not all(isinstance(value, str) and value.strip() for value in (
        stage, status, actor, next_action, outcome,
    )):
        raise ValueError("Inbox task transition fields must be non-empty strings")
    previous = review.get("current") if isinstance(review.get("current"), dict) else None
    current = {
        "stage": stage.strip(), "status": status.strip(), "actor": actor.strip(),
        "next_action": next_action.strip(),
    }
    review.update({"current": current, "updated_at": _now()})
    _append_transition(review, from_current=previous, to_current=current, outcome=outcome.strip())
    _append_step(review, stage=current["stage"], status=current["status"], outcome=outcome.strip())
    path = review.pop("queue_path")
    review.pop("queue_id", None)
    path.write_text(render_markdown(review), encoding="utf-8")
    return True


def suspend_inbox_review(
    knowledge_root: Path, *, intake_id: str, actor: str,
) -> bool:
    """Discard an Inbox review once a separate disposal task owns the next step."""
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("suspending actor must be non-empty")
    review = get_inbox_review(knowledge_root, intake_id)
    if review is None:
        return False
    del actor
    review["queue_path"].unlink(missing_ok=True)
    return True


def _append_step(
    data: Dict[str, object], *, stage: str, status: str, outcome: str,
    reason: Optional[str] = None,
) -> None:
    steps = data.get("step_receipts")
    if not isinstance(steps, list):
        steps = []
    step = {
        "stage": stage,
        "status": status,
        "outcome": outcome,
        "recorded_at": _now(),
    }
    if isinstance(reason, str) and reason.strip():
        step["reason"] = reason.strip()
    steps.append(step)
    data["step_receipts"] = steps


def list_inbox_review_queue(knowledge_root: Path) -> List[Dict[str, object]]:
    root = _queue_root(knowledge_root)
    if not root.is_dir():
        return []
    items: List[Dict[str, object]] = []
    for path in sorted(root.glob("*.md")):
        try:
            data = parse_markdown(path).frontmatter
        except (OSError, ValueError) as error:
            items.append({
                "queue_id": path.stem, "status": "invalid_receipt",
                "queue_path": path.relative_to(root.parent.parent.parent).as_posix(),
                "blocking_reason": f"Inbox task cannot be read: {error}",
                "safe_next_action": "repair_inbox_task_receipt",
            })
            continue
        try:
            _validate_requirement_pii_receipts(data)
        except ValueError as error:
            current = data.get("current")
            items.append({
                "queue_id": path.stem, "intake_id": data.get("intake_id"),
                "inbox_path": data.get("inbox_path"),
                "current_stage": current.get("stage") if isinstance(current, dict) else None,
                "status": "invalid_receipt",
                "queue_path": path.relative_to(root.parent.parent.parent).as_posix(),
                "blocking_reason": str(error),
                "safe_next_action": "repair_inbox_task_receipt",
            })
            continue
        current = data.get("current")
        if not isinstance(current, dict) or current.get("status") != "awaiting_user":
            continue
        items.append({
            "queue_id": path.stem, "intake_id": data.get("intake_id"),
            "inbox_path": data.get("inbox_path"), "current_stage": current.get("stage"),
            "status": current.get("status"), "requirements": _requirements(data),
            "queue_path": path.relative_to(root.parent.parent.parent).as_posix(),
        })
    return items
