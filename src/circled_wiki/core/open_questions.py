"""Persisted administrator questions awaiting a decision or missing input."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4


QUESTION_STATUSES = ("open", "waiting_for_reply", "resolved", "cancelled")


def _write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _cancel_pending_delivery(
    runtime_root: Path, delivery_id: str, *, cancelled_at: str, reason: str
) -> Dict[str, object]:
    if not delivery_id or Path(delivery_id).name != delivery_id:
        raise ValueError("stored question delivery_id is invalid")
    outbox_path = runtime_root / "outbox" / "slack" / f"{delivery_id}.json"
    try:
        payload = json.loads(outbox_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("stored question delivery must resolve to a valid Outbox item") from error
    if payload.get("status") in {"pending_connector_delivery", "ready_for_connector_delivery"}:
        payload["status"] = "cancelled"
        payload["cancelled_at"] = cancelled_at
        payload["cancellation_reason"] = reason
        _write_json_atomic(outbox_path, payload)
    return payload


def record_open_question(
    runtime_root: Path, *, question: str, asked_of: str, context: str,
    related_bundle: Optional[str] = None, related_evidence: Optional[str] = None,
) -> Dict[str, object]:
    if not question.strip() or not asked_of.strip() or not context.strip():
        raise ValueError("question, asked_of, and context must be non-empty")
    question_id = f"question-{uuid4()}"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "question_id": question_id, "status": "open", "asked_of": asked_of.strip(),
        "question": question.strip(), "context": context.strip(), "created_at": now,
        "related_bundle": related_bundle or "", "related_evidence": related_evidence or "",
        "resolution": None,
    }
    path = runtime_root / "awaiting-input" / f"{question_id}.json"
    _write_json_atomic(path, payload)
    return payload


def list_open_questions(runtime_root: Path, *, asked_of: Optional[str] = None) -> List[Dict[str, object]]:
    root = runtime_root / "awaiting-input"
    questions: List[Dict[str, object]] = []
    for path in sorted(root.glob("question-*.json")) if root.is_dir() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("status") not in {"open", "waiting_for_reply"}:
            continue
        if asked_of and payload.get("asked_of") != asked_of:
            continue
        questions.append(payload)
    return questions


def resolve_open_question(
    runtime_root: Path, *, question_id: str, answer: str, actor: str
) -> Dict[str, object]:
    if not question_id.strip() or not answer.strip() or not actor.strip():
        raise ValueError("question_id, answer, and actor must be non-empty")
    path = runtime_root / "awaiting-input" / f"{question_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("question_id must refer to a valid stored question") from error
    if payload.get("status") not in {"open", "waiting_for_reply"}:
        raise ValueError("only open or waiting questions can be resolved")
    resolved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    delivery = payload.get("delivery")
    if isinstance(delivery, dict) and delivery.get("channel") == "slack":
        delivery_id = str(delivery.get("delivery_id", ""))
        _cancel_pending_delivery(
            runtime_root, delivery_id, cancelled_at=resolved_at,
            reason="question_resolved_before_delivery",
        )
    payload["status"] = "resolved"
    payload["resolution"] = {
        "answer": answer.strip(), "actor": actor.strip(),
        "resolved_at": resolved_at,
    }
    _write_json_atomic(path, payload)
    return payload


def queue_slack_decision(
    runtime_root: Path, *, question_id: str, recipient: str
) -> Dict[str, object]:
    """Create a connector-neutral Slack DM request and wait for a linked reply."""
    if not question_id.strip() or not recipient.strip():
        raise ValueError("question_id and recipient must be non-empty")
    path = runtime_root / "awaiting-input" / f"{question_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("question_id must refer to a valid stored question") from error
    if payload.get("status") != "open":
        raise ValueError("only open questions can be queued for Slack")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    delivery = {
        "delivery_id": f"slack-decision-{uuid4()}", "channel": "slack",
        "recipient": recipient.strip(), "question_id": question_id,
        "status": "pending_connector_delivery", "created_at": now,
        "message": f"결정이 필요한 항목입니다.\n\n{payload['question']}\n\n배경: {payload['context']}",
    }
    outbox = runtime_root / "outbox" / "slack" / f"{delivery['delivery_id']}.json"
    _write_json_atomic(outbox, delivery)
    payload["status"] = "waiting_for_reply"
    payload["delivery"] = {
        "channel": "slack", "recipient": recipient.strip(),
        "delivery_id": delivery["delivery_id"], "queued_at": now,
    }
    _write_json_atomic(path, payload)
    return delivery


def claim_slack_decision_delivery(
    runtime_root: Path, *, delivery_id: str
) -> Dict[str, object]:
    """Recheck the linked Question immediately before a connector sends a DM."""
    if not delivery_id.strip() or Path(delivery_id).name != delivery_id:
        raise ValueError("delivery_id must be a safe non-empty identifier")
    outbox_path = runtime_root / "outbox" / "slack" / f"{delivery_id}.json"
    try:
        delivery = json.loads(outbox_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("delivery_id must refer to a valid Slack Outbox item") from error
    if delivery.get("status") == "cancelled":
        return delivery
    if delivery.get("status") not in {"pending_connector_delivery", "ready_for_connector_delivery"}:
        raise ValueError("Slack Outbox item is not claimable")
    question_id = str(delivery.get("question_id", ""))
    if not question_id or Path(question_id).name != question_id:
        raise ValueError("Slack Outbox question_id is invalid")
    question_path = runtime_root / "awaiting-input" / f"{question_id}.json"
    try:
        question = json.loads(question_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("Slack Outbox question must resolve before delivery") from error
    linked = question.get("delivery")
    if (
        question.get("status") != "waiting_for_reply"
        or not isinstance(linked, dict)
        or linked.get("delivery_id") != delivery_id
    ):
        return _cancel_pending_delivery(
            runtime_root, delivery_id,
            cancelled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            reason="question_not_waiting_at_delivery_time",
        )
    delivery["status"] = "ready_for_connector_delivery"
    delivery["claimed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_json_atomic(outbox_path, delivery)
    return delivery


def reconcile_open_question_deliveries(runtime_root: Path) -> Dict[str, object]:
    """Repair stale pending deliveries left by older Runtime versions."""
    outbox_root = runtime_root / "outbox" / "slack"
    cancelled = []
    ready = []
    needs_review = []
    for path in sorted(outbox_root.glob("slack-decision-*.json")) if outbox_root.is_dir() else []:
        try:
            delivery = json.loads(path.read_text(encoding="utf-8"))
            status = delivery.get("status")
            if status not in {"pending_connector_delivery", "ready_for_connector_delivery"}:
                continue
            result = claim_slack_decision_delivery(
                runtime_root, delivery_id=str(delivery.get("delivery_id", ""))
            )
            if result.get("status") == "cancelled":
                cancelled.append(str(result.get("delivery_id", "")))
            else:
                ready.append(str(result.get("delivery_id", "")))
        except (OSError, ValueError) as error:
            needs_review.append({"path": path.name, "error": str(error)})
    return {
        "cancelled_count": len(cancelled),
        "ready_count": len(ready),
        "needs_review_count": len(needs_review),
        "cancelled": cancelled,
        "ready": ready,
        "needs_review": needs_review,
    }
