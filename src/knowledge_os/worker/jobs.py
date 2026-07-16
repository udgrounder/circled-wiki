"""Idempotent maintenance jobs; scheduling is delegated to the host environment."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
from typing import Dict, List
from uuid import uuid4

from knowledge_os.core.curator import propose_update
from knowledge_os.core.frontmatter import FrontmatterError, parse_markdown
from knowledge_os.core.ingest import ingest_evidence, read_conversation_intake
from knowledge_os.core.repository import iter_documents
from knowledge_os.core.service import KnowledgeService
from knowledge_os.core.workflow import TaskStore


@dataclass(frozen=True)
class MaintenanceReport:
    valid: bool
    managed_documents: int
    bundles: int
    evidence_manifests: int
    audit_issues: int
    audit_errors: int

    def as_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


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
        evidence_manifests=sum("evidence" in path.parts and path.name != "index.md" for path in documents),
        audit_issues=int(audit["summary"]["issues"]),
        audit_errors=int(audit["summary"]["errors"]),
    )


def run_curation_batch(knowledge_root: Path, limit: int = 100) -> Dict[str, object]:
    """Build repeatable proposals for pending, non-restricted Evidence."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    pending: List[Dict[str, object]] = []
    skipped_restricted = 0
    for path in iter_documents(knowledge_root):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        data = document.frontmatter
        if data.get("type") != "evidence" or data.get("status") not in {"new", "needs_review"}:
            continue
        extensions = data.get("extensions", {})
        if isinstance(extensions, dict) and extensions.get("visibility") == "restricted":
            skipped_restricted += 1
            continue
        pending.append(propose_update(knowledge_root, str(data["id"])))
        if len(pending) >= limit:
            break
    return {
        "proposal_count": len(pending),
        "skipped_restricted": skipped_restricted,
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
            "checks": ["required_metadata", "provider_folder", "content_checksum", "sensitivity_review"],
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


def ingest_accepted_inbox(knowledge_root: Path, limit: int = 100) -> Dict[str, object]:
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
        if data.get("status") != "accepted":
            continue
        is_file = data.get("content_type") == "file"
        if is_file:
            payload_path = Path(content)
            temporary_path = path.parent / f".ingest-{uuid4()}{payload_path.suffix.lower()}"
            # Keep the Inbox payload intact until Evidence validation succeeds so a
            # failed batch remains retryable.
            shutil.copy2(payload_path, temporary_path)
        else:
            temporary_path = path.parent / f".ingest-{uuid4()}.md"
            temporary_path.write_text(content, encoding="utf-8")
        try:
            captured_at = datetime.fromisoformat(str(data["captured_at"]).replace("Z", "+00:00"))
            capture_details = data.get("capture_details")
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
                pii_scanned=data.get("sensitivity_review") == "completed",
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
