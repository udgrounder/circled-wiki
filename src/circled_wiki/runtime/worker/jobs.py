"""Idempotent maintenance jobs; scheduling is delegated to the host environment."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional, Set
from uuid import uuid4

from circled_wiki.core.curator import propose_update
from circled_wiki.config.settings import load_settings
from circled_wiki.core.frontmatter import FrontmatterError, parse_markdown, render_markdown
from circled_wiki.core.ingest import (
    accept_ready_inbox, ingest_evidence, iter_active_inbox_items,
    read_conversation_intake, rollback_evidence_ingest,
)
from circled_wiki.core.inbox_contracts import (
    CONTRACT_NAME,
    CURATION_CONTRACT_NAME,
    curation_blocker_policy,
    load_curation_contract,
    load_inbox_contract,
)
from circled_wiki.core.inbox_review_queue import (
    complete_inbox_review,
    enqueue_inbox_review,
    has_blocking_inbox_review,
    inbox_review_is_resolved,
    reopen_inbox_data_protection_review,
    reopen_inbox_review_after_ingest_failure,
    review_context,
)
from circled_wiki.core.data_protection_receipt import (
    data_protection_candidate_checksum,
    data_protection_receipt_errors,
)
from circled_wiki.core.repository import iter_documents
from circled_wiki.core.curation_queue import (
    list_curation_queue,
    refresh_curation_queue,
)
from circled_wiki.core.service import KnowledgeService
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


def reconcile_curation(knowledge_root: Path, limit: int = 100) -> Dict[str, object]:
    """Run only contract-authorized Curation analysis and durable Review results.

    The configured Curator may close a valid ``no_bundle`` decision or create a
    Review Queue result.  It never approves meaning changes or applies an
    approved revision through this reconciliation path.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    contract = load_curation_contract(knowledge_root)
    if not load_settings(knowledge_root.resolve().parent).curation.enabled and list_curation_queue(knowledge_root):
        return {
            "contract": {"name": CURATION_CONTRACT_NAME, "version": contract["version"],
                         "path": contract["path"].relative_to(knowledge_root.resolve().parent).as_posix()},
            "status": "configuration_required",
            "reason": "adapter_disabled",
            "next_action": "configure_curation_adapter",
        }
    refresh_curation_queue(knowledge_root)
    stages = contract["contract"]["stages"]
    queued_stage = stages["queued"]
    if queued_stage["action"] != "run_configured_curation_batch":
        raise ValueError("Curation reconciliation contract action is unsupported")
    before = list_curation_queue(knowledge_root)[:limit]
    selected_evidence_ids = {str(item["evidence_id"]) for item in before}
    from circled_wiki.core.curation import run_configured_curation_batch

    actions = run_configured_curation_batch(
        knowledge_root, limit=limit, evidence_ids=selected_evidence_ids,
    )
    outcomes = []
    blocked = []
    for item in actions["items"]:
        result = item.get("result")
        outcome_name = _curation_outcome_name(result)
        outcome = queued_stage["outcomes"][outcome_name]
        evidence_id = item.get("evidence_id")
        outcomes.append({
            "evidence_id": evidence_id,
            "outcome": outcome_name,
            **outcome,
        })
        if outcome_name == "retryable_block":
            retry_policy = curation_blocker_policy(
                str(result.get("reason", "")) if isinstance(result, dict) else ""
            )
            blocked.append({
                "evidence_id": item.get("evidence_id"),
                "stage": "queued",
                "next_action": retry_policy["safe_next_action"],
                "reason_category": retry_policy["category"],
                "reason": str(result.get("reason", "")),
            })
    remaining = [
        item for item in list_curation_queue(knowledge_root)
        if str(item["evidence_id"]) in selected_evidence_ids
    ]
    remaining_ids = {str(item["evidence_id"]) for item in remaining}
    for outcome in outcomes:
        if outcome["queue_disposition"] == "complete" and outcome["evidence_id"] in remaining_ids:
            raise ValueError(
                "Curation reconciliation outcome did not complete its queue item: "
                f"{outcome['evidence_id']}"
            )
    return {
        "contract": {
            "name": CURATION_CONTRACT_NAME,
            "version": contract["version"],
            "path": contract["path"].relative_to(knowledge_root.resolve().parent).as_posix(),
        },
        "before": {"item_count": len(before), "items": before},
        "actions": actions,
        "outcomes": outcomes,
        "blocked": blocked,
        "after": {"items": remaining},
    }


def _curation_outcome_name(result: object) -> str:
    """Classify a Curator result into the contract's fixed outcome vocabulary."""
    if not isinstance(result, dict):
        return "retryable_block"
    action = result.get("action")
    if action == "no_bundle":
        return "no_bundle"
    if action in {"created_review", "reused_review"}:
        return "review_handoff"
    if action == "updated" and result.get("promotion_mode") == "automatic_update":
        return "published"
    promotion = result.get("promotion")
    if isinstance(promotion, dict):
        if promotion.get("status") == "active":
            return "published"
        if promotion.get("status") == "draft":
            return "draft_created"
    return "retryable_block"


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
    for path in iter_active_inbox_items(knowledge_root):
        if len(items) + len(invalid) >= limit:
            break
        result = None
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
        receipt_errors = data_protection_receipt_errors(
            data.get("data_protection_receipt"),
            checksum=str(data.get("checksum", "")), require_resolved=True,
        )
        if receipt_errors and data.get("sensitivity_review") != "required":
            issues.append("data_protection_required")
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
                "sensitivity_review", "data_protection_receipt",
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


def _unlink_workflow_outcome(
    knowledge_root: Path, intake: Dict[str, object], evidence_id: str,
) -> None:
    """Undo an outcome link when the surrounding Inbox transition rolls back."""
    details = intake.get("capture_details")
    if not isinstance(details, dict) or details.get("capture_type") != "workflow_outcome":
        return
    task_id = details.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        return
    try:
        store = TaskStore(knowledge_root.parent / ".runtime")
        task = store.read(task_id)
    except (OSError, ValueError):
        return
    if task.get("outcome_evidence_id") != evidence_id:
        return
    task.pop("outcome_evidence_id", None)
    store.update(task)


def _verify_inbox_evidence_transition(
    knowledge_root: Path, intake_path: Path, intake_id: str, evidence_id: str,
    *, queue_expected: bool, source_absent: bool = True,
) -> None:
    """Verify only the transition artifacts; Evidence content was validated at creation."""
    if source_absent and intake_path.exists():
        raise ValueError("Inbox source remained after Evidence transition")
    if queue_expected and not any(
        str(item.get("evidence_id")) == evidence_id for item in list_curation_queue(knowledge_root)
    ):
        raise ValueError("Curation Queue item is missing after Evidence transition")


def _stage_inbox_source_for_removal(
    intake_path: Path, payload: object, *, is_file: bool,
) -> List[Path]:
    """Move Inbox source files to non-active staging names before cleanup.

    The staged names do not end in ``.md`` and therefore cannot be picked up by
    Inbox reconciliation.  If the second move fails, the first move is
    restored so a retry still has the complete source.
    """
    staged: List[Path] = []
    staged_envelope = intake_path.parent / f".ingest-removed-{uuid4()}.envelope"
    intake_path.replace(staged_envelope)
    staged.append(staged_envelope)
    if is_file:
        payload_path = Path(payload)
        staged_payload = payload_path.parent / f".ingest-removed-{uuid4()}.payload"
        try:
            payload_path.replace(staged_payload)
        except OSError:
            staged_envelope.replace(intake_path)
            raise
        staged.append(staged_payload)
    return staged


def _restore_staged_inbox_source(
    intake_path: Path, payload: object, staged: List[Path], *, is_file: bool,
) -> None:
    """Restore staged Inbox files after a pre-cleanup transition failure."""
    if is_file and len(staged) > 1 and staged[1].exists():
        Path(payload).parent.mkdir(parents=True, exist_ok=True)
        staged[1].replace(Path(payload))
    if staged and staged[0].exists():
        intake_path.parent.mkdir(parents=True, exist_ok=True)
        staged[0].replace(intake_path)


def _rewind_accepted_inbox_to_data_protection(path: Path, data: Dict[str, object]) -> Dict[str, object]:
    """Reopen an accepted candidate when its unified security receipt is absent."""
    if data.get("status") != "accepted":
        return data
    document = parse_markdown(path)
    updated = dict(data)
    updated["status"] = "pending"
    updated.pop("inspection", None)
    updated["sensitivity_review"] = "required"
    updated.pop("data_protection_receipt", None)
    updated.pop("sensitivity_inspection", None)
    updated.pop("pii_scan_receipt", None)
    path.write_text(render_markdown(updated, document.body), encoding="utf-8")
    return updated


def ingest_accepted_inbox(
    knowledge_root: Path, limit: int = 100, *, intake_ids: Optional[Set[str]] = None,
) -> Dict[str, object]:
    """Convert accepted, data-protection-reviewed Inbox items to Evidence.

    The integrated Data Protection stage has already scanned and decided the
    exact candidate.  This worker only validates that receipt and performs the
    transition; it never re-runs or reinterprets PII or sensitivity decisions.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    knowledge_root = knowledge_root.resolve()
    inbox_root = knowledge_root / "inbox"
    ingested: List[Dict[str, object]] = []
    failed: List[Dict[str, str]] = []
    if not inbox_root.is_dir():
        return {"ingested_count": 0, "failed_count": 0, "items": [], "failures": []}
    for path in iter_active_inbox_items(knowledge_root):
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
        # PII Scan and sensitivity review are one completed Data Protection
        # stage. Evidence creation verifies that single checksum-bound Receipt;
        # it does not re-run or reinterpret the security decision.
        receipt = data.get("data_protection_receipt")
        receipt_errors = data_protection_receipt_errors(
            receipt, checksum=str(data.get("checksum", "")),
            candidate_checksum=data_protection_candidate_checksum(data, content),
            require_resolved=True,
        )
        if receipt_errors:
            data = _rewind_accepted_inbox_to_data_protection(path, data)
            reopen_inbox_data_protection_review(
                knowledge_root, intake_id=str(data["id"]), actor="evidence-ingest-agent",
            )
            if not isinstance(receipt, dict) or receipt.get("status") != "awaiting_user":
                enqueue_inbox_review(
                    knowledge_root, intake_id=str(data["id"]), inbox_path=path,
                    current_stage="data_protection", reason_code="data_protection_required",
                )
            failed.append({
                "intake_id": str(data["id"]),
                "path": path.relative_to(knowledge_root).as_posix(),
                "error": "Data Protection Receipt is required before Evidence ingestion",
                "reason_code": "data_protection_required",
            })
            continue
        if has_blocking_inbox_review(knowledge_root, str(data["id"])):
            failed.append({
                "intake_id": str(data["id"]),
                "path": path.relative_to(knowledge_root).as_posix(),
                "error": "inbox review must be resolved before Evidence ingestion",
            })
            continue
        is_file = data.get("content_type") == "file"
        temporary_path: Optional[Path] = None
        staged_source: List[Path] = []
        result = None
        try:
            if is_file:
                payload_path = Path(content)
                temporary_path = path.parent / f".ingest-{uuid4()}{payload_path.suffix.lower()}"
                # Keep the Inbox payload intact until Evidence validation succeeds so a
                # failed batch remains retryable.
                shutil.copy2(payload_path, temporary_path)
            else:
                temporary_path = path.parent / f".ingest-{uuid4()}.md"
                temporary_path.write_text(str(content), encoding="utf-8")
            captured_at = datetime.fromisoformat(str(data["captured_at"]).replace("Z", "+00:00"))
            capture_details = data.get("capture_details")
            source_external_id = (
                str(capture_details.get("external_id")).strip()
                if isinstance(capture_details, dict) and capture_details.get("external_id")
                else None
            )
            inbox_review = review_context(knowledge_root, str(data["id"]))
            if inbox_review is None:
                raise ValueError("resolved Data Protection Receipt and Inbox contract record are required")
            pii_scan = dict(receipt["pii_scan"])
            result = ingest_evidence(
                knowledge_root,
                temporary_path,
                str(data["provider"]),
                why_collected=str(data["why_collected"]),
                intended_use=list(data["intended_use"]),
                title=str(data["title"]),
                source_url=str(data.get("source_url") or "") or None,
                source_locator=str(data.get("source_locator") or "") or None,
                source_external_id=source_external_id,
                captured_from=str(data.get("captured_from", "api")),
                captured_at=captured_at,
                reuse_value="high" if data.get("content_type") == "conversation" else "medium",
                retention_class="outcome" if data.get("content_type") == "conversation" else "general_reference",
                sensitivity_review=str(data.get("sensitivity_review", "required")),
                idempotency_key=str(data["idempotency_key"]),
                content_mode="external_file" if is_file else "embedded",
                capture_fidelity="verbatim",
                pii_scan_receipt=pii_scan,
                data_protection_receipt=dict(receipt),
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
            outcome_linked = _link_workflow_outcome(knowledge_root, data, result.evidence_id)
            if (
                isinstance(capture_details, dict)
                and capture_details.get("capture_type") == "workflow_outcome"
                and not outcome_linked
            ):
                raise ValueError("workflow outcome Evidence linkage failed; Inbox remains retryable")
            staged_source = _stage_inbox_source_for_removal(path, content, is_file=is_file)
            _verify_inbox_evidence_transition(
                knowledge_root, path, str(data["id"]), result.evidence_id,
                queue_expected=not result.reused,
            )
            complete_inbox_review(
                knowledge_root, intake_id=str(data["id"]),
                evidence_id=result.evidence_id,
            )
            cleanup_pending: List[str] = []
            for staged_path in staged_source:
                try:
                    staged_path.unlink(missing_ok=True)
                except OSError:
                    # Evidence and the contract transition are already durable;
                    # leave the non-active staging file for a later cleanup pass.
                    cleanup_pending.append(staged_path.name)
            ingested.append({
                "intake_id": data["id"],
                "evidence_id": result.evidence_id,
                "evidence_path": result.manifest_path.relative_to(
                    knowledge_root.parent.resolve()
                ).as_posix(),
                "reused": result.reused,
                "outcome_linked": outcome_linked,
                "data_protection_status": str(receipt["status"]),
                "pii_scan_result": str(pii_scan.get("result", "")),
                **({"cleanup_pending": cleanup_pending} if cleanup_pending else {}),
            })
        except (OSError, ValueError, KeyError, TypeError) as error:
            cleanup_errors: List[str] = []
            if staged_source:
                try:
                    _restore_staged_inbox_source(path, content, staged_source, is_file=is_file)
                except (OSError, ValueError) as cleanup_error:
                    cleanup_errors.append("source restore failed: " + str(cleanup_error))
            if result is not None:
                try:
                    _unlink_workflow_outcome(knowledge_root, data, result.evidence_id)
                except (OSError, ValueError) as cleanup_error:
                    cleanup_errors.append("workflow outcome rollback failed: " + str(cleanup_error))
            if result is not None:
                try:
                    rollback_evidence_ingest(knowledge_root, result)
                except (OSError, ValueError) as cleanup_error:
                    cleanup_errors.append("Evidence rollback failed: " + str(cleanup_error))
            try:
                reopen_inbox_review_after_ingest_failure(
                    knowledge_root, intake_id=str(data.get("id", "")),
                    reason=str(error),
                )
            except (OSError, ValueError) as cleanup_error:
                cleanup_errors.append("Inbox retry transition failed: " + str(cleanup_error))
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    cleanup_errors.append("temporary source cleanup failed: " + str(cleanup_error))
            failure_error = str(error)
            if cleanup_errors:
                failure_error += " (" + "; ".join(cleanup_errors) + ")"
            failed.append({
                "intake_id": str(data.get("id", "")),
                "path": path.relative_to(knowledge_root).as_posix(),
                "error": failure_error,
                "reason_code": "evidence_ingest_retry",
            })
    return {
        "ingested_count": len(ingested),
        "failed_count": len(failed),
        "items": ingested,
        "failures": failed,
    }


def _reconciliation_snapshot(knowledge_root: Path, limit: int) -> List[Dict[str, str]]:
    """Fix one bounded set of valid pending/accepted items for a reconciliation run."""
    snapshot: List[Dict[str, str]] = []
    for path in iter_active_inbox_items(knowledge_root):
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
    for path in iter_active_inbox_items(knowledge_root):
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
    can accept already-ready items and run the automatic PII Scan for accepted
    items, but leaves sensitivity_review decisions and safe handling after a
    PII needs_review result in their existing queue.
    """
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    from circled_wiki.core.inbox_review_queue import reconcile_orphaned_inbox_reviews

    orphaned = reconcile_orphaned_inbox_reviews(knowledge_root, actor=actor)
    contract = load_inbox_contract(knowledge_root)
    before = _reconciliation_snapshot(knowledge_root, limit)
    intake_ids = {item["intake_id"] for item in before}
    stages = contract["contract"]["stages"]
    pending_action = stages["pending"]["action"]
    accepted_action = stages["accepted"]["action"]
    if pending_action != "accept_ready_inbox" or accepted_action != "ingest_accepted":
        raise ValueError("Inbox reconciliation contract action is unsupported")
    accepted = accept_ready_inbox(knowledge_root, actor, limit=limit, intake_ids=intake_ids)
    ingested = ingest_accepted_inbox(
        knowledge_root, limit=limit, intake_ids=intake_ids,
    )
    blocked = [
        {
            "intake_id": item["intake_id"],
            "stage": "pending",
            "next_action": stages["pending"]["on_blocked"]["task_contract"],
            "reasons": [item["reason"]],
        }
        for item in accepted["skipped"]
    ]
    blocked.extend(
        {
            "intake_id": failure["intake_id"],
            "stage": "accepted",
            "next_action": stages["accepted"]["on_blocked"]["task_contract"],
            "reasons": [str(failure.get("reason_code") or failure["error"])],
        }
        for failure in ingested["failures"]
        if failure["error"] == "inbox review must be resolved before Evidence ingestion"
        or failure.get("reason_code") in {
            "pii_scan_required", "pii_needs_review", "data_protection_required",
            "evidence_ingest_retry",
        }
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
        "orphaned": [
            dict(item)
            for item in orphaned
        ],
        "after": {"items": sorted(after, key=lambda item: item["intake_id"])},
    }


def reconcile_inbox_then_curation(
    knowledge_root: Path, actor: str, limit: int = 100,
) -> Dict[str, object]:
    """Finish safe Inbox reconciliation before starting one Curation batch.

    A scheduler can use this as its single entry point without treating an
    arbitrary Agent conversation as proof that Inbox work completed.  Any
    unresolved Inbox gate or ingestion failure prevents Curation from running.
    """
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")

    inbox_runs: List[Dict[str, object]] = []
    while True:
        inbox = reconcile_inbox(knowledge_root, actor, limit=limit)
        inbox_runs.append(inbox)
        failures = list(inbox["ingested"]["failures"])
        blocked = list(inbox["blocked"])
        if blocked or failures:
            return {
                "status": "inbox_blocked",
                "inbox": {"runs": inbox_runs, "blocked": blocked, "failures": failures},
                "curation": {
                    "status": "skipped",
                    "reason": "inbox_reconciliation_incomplete",
                },
            }
        if inbox["before"]["item_count"] == 0:
            break
        incomplete = [
            item for item in inbox["after"]["items"]
            if item.get("status") in {"pending", "accepted"}
        ]
        if incomplete:
            return {
                "status": "inbox_incomplete",
                "inbox": {"runs": inbox_runs, "remaining": incomplete},
                "curation": {
                    "status": "skipped",
                    "reason": "inbox_reconciliation_incomplete",
                },
            }

    queue = list_curation_queue(knowledge_root)
    if not queue:
        return {
            "status": "no_curation_work",
            "inbox": {"runs": inbox_runs},
            "curation": {"status": "skipped", "reason": "curation_queue_empty"},
        }
    return {
        "status": "curation_started",
        "inbox": {"runs": inbox_runs},
        "queue": {"item_count": len(queue), "items": queue},
        "curation": reconcile_curation(knowledge_root, limit=limit),
    }
