"""Derived governance views and non-mutating knowledge quality checks."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .repository import find_document_by_id, iter_documents
from .evidence import evidence_original_bytes
from .validator import verify_evidence_original


CLAIM_SUPPORT_STATUSES = {"verified", "limited", "inferred", "needs_review"}
VISIBLE_BUNDLE_STATUSES = {"active"}


def _is_restricted(frontmatter: Dict[str, Any]) -> bool:
    extensions = frontmatter.get("extensions")
    return isinstance(extensions, dict) and extensions.get("visibility") == "restricted"


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value.strip():
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


def _open_tasks(runtime_root: Path) -> List[Dict[str, Any]]:
    tasks_root = runtime_root / "tasks"
    if not tasks_root.is_dir():
        return []
    tasks: List[Dict[str, Any]] = []
    import json

    for path in sorted(tasks_root.glob("*.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if task.get("status") not in {"completed", "failed", "needs_review"} and not task.get(
            "outcome_evidence_id"
        ):
            tasks.append(task)
    return tasks


def list_knowledge_inventory(
    knowledge_root: Path,
    runtime_root: Path,
    *,
    domain: Optional[str] = None,
    document_type: Optional[str] = None,
    status: Optional[str] = None,
    owner: Optional[str] = None,
    freshness_state: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return a Frontmatter-derived inventory; never persist a second source of truth."""
    open_tasks = _open_tasks(runtime_root)
    now = datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    for path in iter_documents(knowledge_root):
        if "bundles" not in path.parts or path.name in {"index.md", "log.md"}:
            continue
        from .frontmatter import parse_markdown

        data = parse_markdown(path).frontmatter
        if _is_restricted(data):
            continue
        relative = path.relative_to(knowledge_root / "bundles")
        item_domain = relative.parts[0] if relative.parts else ""
        extensions = data.get("extensions", {})
        governance = extensions.get("governance", {}) if isinstance(extensions, dict) else {}
        due_at = _as_datetime(governance.get("review_due_at")) if isinstance(governance, dict) else None
        item_freshness = "unknown" if due_at is None else ("expired" if due_at <= now else "valid")
        owners = data.get("owners", []) if isinstance(data.get("owners"), list) else []
        if domain and item_domain != domain:
            continue
        if document_type and data.get("type") != document_type:
            continue
        if status and data.get("status") != status:
            continue
        if owner and owner not in owners:
            continue
        if freshness_state and item_freshness != freshness_state:
            continue
        bundle_id = str(data.get("id", ""))
        workflow = extensions.get("workflow", {}) if isinstance(extensions, dict) else {}
        workflow_id = workflow.get("workflow_id") if isinstance(workflow, dict) else None
        related_tasks = [
            task for task in open_tasks
            if task.get("workflow_bundle_id") == bundle_id
            or (workflow_id and task.get("target_workflow_id") == workflow_id)
        ]
        inquiry = extensions.get("inquiry", {}) if isinstance(extensions, dict) else {}
        evidence_states = []
        for evidence_id in data.get("evidence", []):
            evidence = find_document_by_id(knowledge_root, str(evidence_id))
            if evidence is not None and _is_restricted(evidence.frontmatter):
                evidence = None
            evidence_extensions = evidence.frontmatter.get("extensions", {}) if evidence else {}
            evidence_states.append(
                evidence_extensions.get("availability", "missing")
                if isinstance(evidence_extensions, dict) else "missing"
            )
        rows.append({
            "id": bundle_id,
            "title": data.get("title"),
            "domain": item_domain,
            "type": data.get("type"),
            "status": data.get("status"),
            "owners": owners,
            "knowledge_revision": extensions.get("knowledge_revision") if isinstance(extensions, dict) else None,
            "updated_at": data.get("updated_at"),
            "reviewed_at": governance.get("reviewed_at") if isinstance(governance, dict) else None,
            "review_due_at": governance.get("review_due_at") if isinstance(governance, dict) else None,
            "freshness_state": item_freshness,
            "evidence_availability": sorted(set(evidence_states)),
            "open_task_ids": [task.get("task_id") for task in related_tasks],
            "open_inquiry": bool(isinstance(inquiry, dict) and inquiry.get("status") in {"open", "investigating"}),
            "path": path.relative_to(knowledge_root.parent).as_posix(),
        })
    return sorted(rows, key=lambda row: (str(row["domain"]), str(row["type"]), str(row["title"])))


def audit_knowledge(knowledge_root: Path, runtime_root: Path) -> Dict[str, Any]:
    """Report actionable governance issues without changing official knowledge."""
    inventory = list_knowledge_inventory(knowledge_root, runtime_root)
    issues: List[Dict[str, Any]] = []
    for row in inventory:
        document = find_document_by_id(knowledge_root, str(row["id"]))
        if document is None:
            continue
        data = document.frontmatter
        if row["status"] == "active" and not row["owners"]:
            issues.append(_issue("error", "missing_owner", row["id"], "Active Bundle has no owner"))
        if row["status"] == "active" and row["freshness_state"] == "expired":
            issues.append(_issue("warning", "review_overdue", row["id"], "Active Bundle review is overdue"))
        if any(state != "available" for state in row["evidence_availability"]):
            issues.append(_issue("warning", "evidence_unavailable", row["id"], "Bundle has unavailable Evidence"))
        if row["open_inquiry"]:
            issues.append(_issue("info", "open_inquiry", row["id"], "Bundle has an unresolved Inquiry"))
        links = data.get("links", [])
        if row["status"] == "active" and (not isinstance(links, list) or not links):
            issues.append(_issue("info", "unlinked_bundle", row["id"], "Active Bundle has no related Bundle links"))
    for task in _open_tasks(runtime_root):
        created_at = _as_datetime(task.get("created_at"))
        if created_at and (datetime.now(timezone.utc) - created_at).days >= 30:
            issues.append(_issue("warning", "stale_runtime_task", task.get("task_id"), "Open Task is at least 30 days old"))
    active_keys: Dict[tuple[str, str, str], List[str]] = {}
    for row in inventory:
        if row["status"] != "active":
            continue
        key = (
            str(row["domain"]), str(row["type"]),
            " ".join(str(row["title"]).casefold().split()),
        )
        active_keys.setdefault(key, []).append(str(row["id"]))
    for ids in active_keys.values():
        if len(ids) > 1:
            for document_id in ids:
                issues.append(_issue(
                    "warning", "duplicate_active_title", document_id,
                    "Multiple Active Bundles share the same domain, type, and normalized title",
                ))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "bundles": len(inventory),
            "issues": len(issues),
            "errors": sum(issue["severity"] == "error" for issue in issues),
            "warnings": sum(issue["severity"] == "warning" for issue in issues),
        },
        "issues": issues,
        "archive_candidates": [row["id"] for row in inventory if row["status"] == "deprecated"],
    }


def validate_claim_support(knowledge_root: Path, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a transport-level claim/evidence contract without persisting an answer."""
    errors: List[str] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not str(claim.get("claim", "")).strip():
            errors.append(f"claims[{index}].claim must be non-empty")
            continue
        status = claim.get("support_status")
        if status not in CLAIM_SUPPORT_STATUSES:
            errors.append(f"claims[{index}].support_status is invalid")
            continue
        evidence_ids = claim.get("evidence_ids", [])
        if not isinstance(evidence_ids, list):
            errors.append(f"claims[{index}].evidence_ids must be an array")
            continue
        if status in {"verified", "limited"} and not evidence_ids:
            errors.append(f"claims[{index}] requires Evidence")
        for evidence_id in evidence_ids:
            evidence = find_document_by_id(knowledge_root, str(evidence_id))
            if evidence is None or evidence.frontmatter.get("type") != "evidence":
                errors.append(f"claims[{index}] Evidence does not resolve: {evidence_id}")
                continue
            if _is_restricted(evidence.frontmatter):
                errors.append(f"claims[{index}] Evidence is restricted")
                continue
            extensions = evidence.frontmatter.get("extensions", {})
            if status == "verified" and (
                not isinstance(extensions, dict) or extensions.get("availability") != "available"
            ):
                errors.append(f"claims[{index}] verified Evidence must be available")
            elif status == "verified":
                integrity_error = verify_evidence_original(evidence)
                if integrity_error:
                    errors.append(f"claims[{index}] {integrity_error}")
    return {
        "valid": not errors,
        "errors": errors,
        "claim_count": len(claims),
        "validation_scope": "structure_and_evidence_integrity",
        "semantic_entailment_validated": False,
    }


def measure_runbook_effectiveness(knowledge_root: Path, workflow_id: str) -> Dict[str, Any]:
    """Derive outcome counts by knowledge revision for before/after review."""
    revisions: Dict[int, Dict[str, int]] = {}
    from .frontmatter import parse_markdown

    for path in iter_documents(knowledge_root):
        if "evidence" not in path.parts or path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        if _is_restricted(document.frontmatter):
            continue
        try:
            original_bytes = evidence_original_bytes(document)
            if original_bytes is None:
                continue
            payload = json.loads(original_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        target_id = payload.get("target_workflow_id") or payload.get("workflow_id")
        if payload.get("type") != "workflow-outcome" or target_id != workflow_id:
            continue
        revision = payload.get("knowledge_revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            continue
        metric = revisions.setdefault(revision, {
            "total": 0, "completed": 0, "failed": 0, "needs_review": 0, "with_feedback": 0,
        })
        metric["total"] += 1
        status = payload.get("status")
        if status in {"completed", "failed", "needs_review"}:
            metric[status] += 1
        if str(payload.get("feedback", "")).strip():
            metric["with_feedback"] += 1
    rows = []
    for revision in sorted(revisions):
        metric = revisions[revision]
        total = metric["total"]
        rows.append({
            "knowledge_revision": revision,
            **metric,
            "completion_rate": metric["completed"] / total if total else 0.0,
        })
    return {
        "workflow_id": workflow_id,
        "revisions": rows,
        "comparable": len(rows) >= 2 and all(row["total"] > 0 for row in rows[-2:]),
    }


def _issue(severity: str, code: str, document_id: Any, message: str) -> Dict[str, Any]:
    return {"severity": severity, "code": code, "document_id": document_id, "message": message}
