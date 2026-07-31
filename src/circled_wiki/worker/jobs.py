"""Idempotent maintenance jobs; scheduling is delegated to the host environment."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional, Set
from uuid import uuid4

from circled_wiki.core.curator import propose_update
from circled_wiki.core.frontmatter import FrontmatterError, parse_markdown
from circled_wiki.core.ingest import accept_ready_inbox, ingest_evidence, read_conversation_intake
from circled_wiki.core.inbox_contracts import CONTRACT_NAME, load_inbox_contract
from circled_wiki.core.inbox_review_queue import (
    complete_inbox_review,
    has_blocking_inbox_review,
    review_context,
)
from circled_wiki.core.repository import iter_documents
from circled_wiki.core.curation_queue import list_curation_queue
from circled_wiki.core.service import KnowledgeService
from circled_wiki.core.sensitive_data import redact_sensitive_data
from circled_wiki.core.workflow import TaskStore


@dataclass(frozen=True)
class MaintenanceReport:
    valid: bool
    managed_documents: int
    bundles: int
    evidence_records: int
    audit_issues: int
    audit_errors: int

    def as_dict(self) -> Dict[str, object]:
        payload = self.__dict__.copy()
        # Compatibility alias for existing scheduler consumers.
        payload["evidence_manifests"] = self.evidence_records
        return payload

    @property
    def evidence_manifests(self) -> int:
        """Deprecated compatibility alias; use evidence_records."""
        return self.evidence_records


def run_maintenance(knowledge_root: Path) -> MaintenanceReport:
    """Run a read-only, repeatable maintenance pass suitable for a scheduler."""
    service = KnowledgeService(knowledge_root)
    validation = service.validate_result()
    audit = service.audit_knowledge()
    documents = list(iter_documents(knowledge_root))
    return MaintenanceReport(
        valid=bool(validation["valid"]),
        managed_documents=len(documents),
        bundles=sum("bundles" in path.parts and path.name != "index.md" for path in documents),
        evidence_records=sum("evidence" in path.parts and path.name != "index.md" for path in documents),
        audit_issues=int(audit["summary"]["issues"]),
        audit_errors=int(audit["summary"]["errors"]),
    )


def run_curation_batch(knowledge_root: Path, limit: int = 100) -> Dict[str, object]:
    """Build repeatable proposals for pending, non-restricted Evidence."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    pending: List[Dict[str, object]] = []
    skipped_restricted = 0
    search_cache = {}
    queued_ids = {str(item["evidence_id"]) for item in list_curation_queue(knowledge_root)}
    for path in iter_documents(knowledge_root):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        data = document.frontmatter
        if data.get("type") != "evidence":
            continue
        if str(data.get("id")) not in queued_ids:
            continue
        extensions = data.get("extensions", {})
        if isinstance(extensions, dict) and extensions.get("visibility") == "restricted":
            skipped_restricted += 1
            continue
        pending.append(propose_update(
            knowledge_root, str(data["id"]), search_cache=search_cache,
        ))
        if len(pending) >= limit:
            break
    return {
        "proposal_count": len(pending),
        "skipped_restricted": skipped_restricted,
        "cached_searches": len(search_cache),
        "proposals": pending,
    }


def inspect_inbox(knowledge_root: Path, limit: int = 100) -> Dict[str, object]:
    """Read-only inspection of pending conversation, document, and file Inbox items."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    knowledge_root = knowledge_root.resolve()
    inbox_root = knowledge_root / "inbox"
    items: List[Dict[str, object]] = []
    invalid: List[Dict[str, str]] = []
    skipped_unmanaged = 0
    unmanaged_files: List[Dict[str, str]] = []
    if not inbox_root.is_dir():
        return {
            "item_count": 0,
            "invalid_count": 0,
            "skipped_unmanaged": 0,
            "items": [],
            "invalid": [],
        }
    for path in sorted(inbox_root.iterdir()):
        if path.is_file():
            inbox_relative = path.relative_to(inbox_root).as_posix()
            unmanaged_files.append({
                "path": path.relative_to(knowledge_root).as_posix(),
                "recovery": (
                    "Use capture-file --inbox-file "
                    f"'{inbox_relative}' with the required provider and metadata."
                ),
            })
            skipped_unmanaged += 1
    for path in sorted(inbox_root.glob("*/*.md")):
        if len(items) + len(invalid) >= limit:
            break
        try:
            data, _ = read_conversation_intake(path)
        except FrontmatterError:
            skipped_unmanaged += 1
            continue
        except (OSError, ValueError) as error:
            invalid.append({"path": path.relative_to(knowledge_root).as_posix(), "error": str(error)})
            continue
        if data.get("status") != "pending":
            continue
        issues = []
        if data.get("sensitivity_review") == "required":
            issues.append("sensitivity_review_required")
        items.append({
            "intake_id": data["id"],
            "path": path.relative_to(knowledge_root).as_posix(),
            "provider": data["provider"],
            "content_type": data["content_type"],
            "status": data["status"],
            "gate_status": "blocked" if issues else "ready_for_acceptance",
            "issues": issues,
            "checks": [
                "required_metadata", "provider_folder", "content_checksum",
                "sensitivity_review",
            ],
        })
    return {
        "item_count": len(items),
        "invalid_count": len(invalid),
        "skipped_unmanaged": skipped_unmanaged,
        "unmanaged_files": unmanaged_files,
        "items": items,
        "invalid": invalid,
    }


def _link_workflow_outcome(
    knowledge_root: Path, intake: Dict[str, object], evidence_id: str
) -> bool:
    """Link an accepted workflow-outcome Inbox item after its Evidence exists."""
    details = intake.get("capture_details")
    if not isinstance(details, dict) or details.get("capture_type") != "workflow_outcome":
        return False
    task_id = details.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        return False
    try:
        store = TaskStore(knowledge_root.parent / ".runtime")
        task = store.read(task_id)
    except (OSError, ValueError):
        return False
    if task.get("outcome_intake_id") != intake.get("id"):
        return False
    if task.get("outcome_evidence_id") and task.get("outcome_evidence_id") != evidence_id:
        return False
    task["outcome_evidence_id"] = evidence_id
    store.update(task)
    return True


def ingest_accepted_inbox(
    knowledge_root: Path, limit: int = 100, *, intake_ids: Optional[Set[str]] = None,
) -> Dict[str, object]:
    """Convert accepted Inbox items to Evidence without running curation."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    knowledge_root = knowledge_root.resolve()
    inbox_root = knowledge_root / "inbox"
    ingested: List[Dict[str, object]] = []
    failed: List[Dict[str, str]] = []
    if not inbox_root.is_dir():
        return {"ingested_count": 0, "failed_count": 0, "items": [], "failures": []}
    for path in sorted(inbox_root.glob("*/*.md")):
        if len(ingested) + len(failed) >= limit:
            break
        try:
            data, content = read_conversation_intake(path)
        except (FrontmatterError, OSError, ValueError):
            continue
        if intake_ids is not None and str(data.get("id")) not in intake_ids:
            continue
        if data.get("status") != "accepted":
            continue
        if has_blocking_inbox_review(
            knowledge_root, str(data["id"]), str(data["checksum"])
        ):
            failed.append({
                "intake_id": str(data["id"]),
                "path": path.relative_to(knowledge_root).as_posix(),
                "error": "inbox review must be resolved before Evidence ingestion",
            })
            continue
        is_file = data.get("content_type") == "file"
        sensitive_categories: tuple[str, ...] = ()
        if is_file:
            payload_path = Path(content)
            temporary_path = path.parent / f".ingest-{uuid4()}{payload_path.suffix.lower()}"
            # Keep the Inbox payload intact until Evidence validation succeeds so a
            # failed batch remains retryable.
            shutil.copy2(payload_path, temporary_path)
        else:
            # Recheck immediately before Evidence conversion.  Capture may have
            # been performed by any Agent or an older adapter, so never assume
            # its first pass is still sufficient.  Only the policy-scoped values
            # are transformed and no matched value is written to the result.
            precheck = redact_sensitive_data(str(content))
            sensitive_categories = precheck.categories
            temporary_path = path.parent / f".ingest-{uuid4()}.md"
            temporary_path.write_text(precheck.content, encoding="utf-8")
        try:
            captured_at = datetime.fromisoformat(str(data["captured_at"]).replace("Z", "+00:00"))
            capture_details = data.get("capture_details")
            inbox_review = review_context(
                knowledge_root, str(data["id"]), str(data["checksum"])
            )
            result = ingest_evidence(
                knowledge_root,
                temporary_path,
                str(data["provider"]),
                why_collected=str(data["why_collected"]),
                intended_use=list(data["intended_use"]),
                title=str(data["title"]),
                source_url=str(data.get("source_url") or "") or None,
                source_locator=str(data.get("source_locator") or "") or None,
                captured_from=str(data.get("captured_from", "api")),
                captured_at=captured_at,
                reuse_value="high" if data.get("content_type") == "conversation" else "medium",
                retention_class="outcome" if data.get("content_type") == "conversation" else "general_reference",
                sensitivity_review=str(data.get("sensitivity_review", "required")),
                idempotency_key=str(data["idempotency_key"]),
                content_mode="external_file" if is_file else "embedded",
                capture_fidelity="verbatim",
                pii_scan_receipt=(
                    data.get("pii_scan_receipt")
                    if isinstance(data.get("pii_scan_receipt"), dict) else None
                ),
                inbox_review=inbox_review,
                capture_details=(
                    capture_details if data.get("content_type") == "conversation" and isinstance(capture_details, dict) else None
                ),
                original_stem=(
                    Path(str(data["payload_file"])).stem if is_file else re.sub(
                    r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    "",
                    path.stem,
                    flags=re.IGNORECASE,
                    )
                ),
            )
            if inbox_review is not None:
                complete_inbox_review(
                    knowledge_root, intake_id=str(data["id"]),
                    source_checksum=str(data["checksum"]), evidence_id=result.evidence_id,
                )
            outcome_linked = _link_workflow_outcome(knowledge_root, data, result.evidence_id)
            path.unlink()
            if is_file:
                Path(content).unlink(missing_ok=True)
            ingested.append({
                "intake_id": data["id"],
                "evidence_id": result.evidence_id,
                "evidence_path": result.manifest_path.relative_to(
                    knowledge_root.parent.resolve()
                ).as_posix(),
                "reused": result.reused,
                "outcome_linked": outcome_linked,
                "sensitive_data_recheck": {
                    "masked": bool(sensitive_categories),
                    "categories": list(sensitive_categories),
                },
            })
        except (OSError, ValueError, KeyError, TypeError) as error:
            temporary_path.unlink(missing_ok=True)
            failed.append({"path": path.relative_to(knowledge_root).as_posix(), "error": str(error)})
    return {
        "ingested_count": len(ingested),
        "failed_count": len(failed),
        "items": ingested,
        "failures": failed,
    }


def _reconciliation_snapshot(knowledge_root: Path, limit: int) -> List[Dict[str, str]]:
    """Fix one bounded set of valid pending/accepted items for a reconciliation run."""
    snapshot: List[Dict[str, str]] = []
    for path in sorted((knowledge_root.resolve() / "inbox").glob("*/*.md")):
        if len(snapshot) >= limit:
            break
        try:
            data, _ = read_conversation_intake(path)
        except (FrontmatterError, OSError, ValueError):
            continue
        status = str(data.get("status", ""))
        if status not in {"pending", "accepted"}:
            continue
        snapshot.append({"intake_id": str(data["id"]), "status": status})
    return snapshot


def _reconciliation_after_state(knowledge_root: Path, intake_ids: Set[str]) -> List[Dict[str, str]]:
    """Report remaining Inbox state for the fixed run set without inferring outcomes."""
    remaining: List[Dict[str, str]] = []
    for path in sorted((knowledge_root.resolve() / "inbox").glob("*/*.md")):
        try:
            data, _ = read_conversation_intake(path)
        except (FrontmatterError, OSError, ValueError):
            continue
        intake_id = str(data.get("id", ""))
        if intake_id in intake_ids:
            remaining.append({"intake_id": intake_id, "status": str(data.get("status", ""))})
    return remaining


def reconcile_inbox(knowledge_root: Path, actor: str, limit: int = 100) -> Dict[str, object]:
    """Advance Inbox items through contract-authorized, non-judgmental stages.

    The contract is deliberately a dispatcher, not an approval substitute.  It
    can accept already-ready items and ingest accepted items, but leaves human
    sensitivity/PII decisions and blocking review work in their existing queue.
    """
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    contract = load_inbox_contract(knowledge_root)
    before = _reconciliation_snapshot(knowledge_root, limit)
    intake_ids = {item["intake_id"] for item in before}
    stages = contract["contract"]["stages"]
    pending_action = stages["pending"]["action"]
    accepted_action = stages["accepted"]["action"]
    if pending_action != "accept_ready_inbox" or accepted_action != "ingest_accepted":
        raise ValueError("Inbox reconciliation contract action is unsupported")
    accepted = accept_ready_inbox(knowledge_root, actor, limit=limit, intake_ids=intake_ids)
    ingested = ingest_accepted_inbox(knowledge_root, limit=limit, intake_ids=intake_ids)
    blocked = [
        {
            "intake_id": item["intake_id"],
            "stage": "pending",
            "next_action": stages["pending"]["on_blocked"],
            "reasons": [item["reason"]],
        }
        for item in accepted["skipped"]
    ]
    blocked.extend(
        {
            "intake_id": failure["intake_id"],
            "stage": "accepted",
            "next_action": stages["accepted"]["on_blocked"],
            "reasons": [failure["error"]],
        }
        for failure in ingested["failures"]
        if failure["error"] == "inbox review must be resolved before Evidence ingestion"
    )
    evidence_ids = {str(item["intake_id"]): str(item["evidence_id"]) for item in ingested["items"]}
    after = _reconciliation_after_state(knowledge_root, intake_ids)
    after.extend(
        {"intake_id": intake_id, "status": "evidence", "evidence_id": evidence_id}
        for intake_id, evidence_id in sorted(evidence_ids.items())
    )
    return {
        "contract": {
            "name": CONTRACT_NAME,
            "version": contract["version"],
            "path": contract["path"].relative_to(knowledge_root.resolve().parent).as_posix(),
        },
        "before": {"item_count": len(before), "items": before},
        "accepted": accepted,
        "ingested": ingested,
        "blocked": blocked,
        "after": {"items": sorted(after, key=lambda item: item["intake_id"])},
    }
