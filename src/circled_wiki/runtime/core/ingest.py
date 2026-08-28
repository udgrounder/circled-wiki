"""Evidence ingestion that preserves originals and creates an OKF manifest."""

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from functools import wraps
import hashlib
import inspect
from pathlib import Path
import re
import shutil
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional
from uuid import uuid4

from .frontmatter import FrontmatterError, parse_markdown, render_markdown
from .inbox_review_queue import (
    enqueue_inbox_review,
    escalate_inbox_sensitivity_review,
    advance_inbox_task,
    ensure_inbox_task,
    has_blocking_inbox_review,
    inbox_review_is_resolved,
    reopen_inbox_data_protection_review,
    resolve_inbox_review_requirement,
    review_context,
)
from .data_protection_receipt import (
    build_data_protection_receipt,
    data_protection_candidate_checksum,
    data_protection_receipt_errors,
)
from .namespace import require_stable_organization_id
from .pii import pii_scan_receipt_errors
from .sensitive_data import REDACTED_VALUE, redact_sensitive_data
from circled_wiki.config.data_protection import (
    POLICY_PATH,
    load_data_protection_policy,
    resolve_policy_context,
)
from .evidence import (
    EMBEDDED_FORMAT_VERSION,
    evidence_original_path,
    render_embedded_body,
)
from .validator import validate_document


MAX_GIT_EVIDENCE_BYTES = 10 * 1024 * 1024
SENSITIVITY_POLICY_REF = "inbox-sensitivity/v1"
SENSITIVITY_REQUIRED_CHECKS = {
    "source_access_scope",
    "personal_context",
    "confidential_business_context",
    "publication_scope",
}


def _safe_data_protection_text(
    value: str, findings: Optional[List[Dict[str, object]]] = None,
) -> str:
    """Mask known PII and transient Agent finding values before persistence."""
    safe = redact_sensitive_data(value, mask_policy_categories=True).content
    for finding in findings or []:
        finding_value = finding.get("value") if isinstance(finding, dict) else None
        if isinstance(finding_value, str) and finding_value:
            safe = safe.replace(finding_value, REDACTED_VALUE)
    return safe


def _write_data_protection_receipt(
    path: Path, *, pii_scan: Dict[str, object], policy, actor: str,
    sensitivity_decision: str, context: str, matched_categories: List[str],
    agent_masked_findings: List[Dict[str, object]], resolution: str,
    rationale: str,
) -> Dict[str, object]:
    """Persist the single Inbox data-protection receipt and safe projections."""
    document = parse_markdown(path)
    data, content = read_conversation_intake(path)
    allowed_contexts = set(policy.agent_mask_categories)
    safe_context = context.strip() if isinstance(context, str) and context.strip() in allowed_contexts else ""
    safe_rationale = _safe_data_protection_text(rationale, agent_masked_findings)
    safe_resolution = resolution.strip() if resolution.strip() in {
        "no_policy_candidates", "no_mask_target", "awaiting_user",
        "pii_needs_review", "compatibility_receipt",
    } else "awaiting_user"
    receipt = build_data_protection_receipt(
        source_checksum=str(data["checksum"]), pii_scan=pii_scan,
        candidate_checksum=data_protection_candidate_checksum(data, content),
        policy_ref=policy.policy_ref, policy_config=POLICY_PATH,
        policy_config_version=policy.schema_version, actor=actor,
        sensitivity_decision=sensitivity_decision, context=safe_context,
        matched_categories=matched_categories,
        agent_masked_findings=agent_masked_findings, resolution=safe_resolution,
    )
    metadata = dict(data)
    if sensitivity_decision in {"completed", "not_applicable"}:
        metadata["sensitivity_review"] = sensitivity_decision
    metadata["data_protection_receipt"] = receipt
    # Compatibility projections remain derived from the unified receipt.  New
    # Inbox/Evidence gates use data_protection_receipt as the source of truth.
    metadata["pii_scan_receipt"] = dict(pii_scan)
    inspection = dict(metadata.get("sensitivity_inspection", {}))
    inspection.update({
        "policy_ref": policy.policy_ref,
        "policy_config": POLICY_PATH,
        "policy_config_version": policy.schema_version,
        "source_checksum": data["checksum"],
        "actor": actor.strip(),
        "checked_at": receipt["recorded_at"],
        "checks": sorted(SENSITIVITY_REQUIRED_CHECKS),
        "matched_categories": list(matched_categories),
        "decision": sensitivity_decision,
        "rationale": safe_rationale,
        "data_protection": receipt["sensitivity"],
    })
    metadata["sensitivity_inspection"] = inspection
    path.write_text(render_markdown(metadata, document.body), encoding="utf-8")
    return receipt


def _read_data_protection_receipt(path: Path, *, require_resolved: bool = False) -> Dict[str, object]:
    """Read and validate the canonical receipt for one current Inbox candidate."""
    data, _ = read_conversation_intake(path)
    receipt = data.get("data_protection_receipt")
    errors = data_protection_receipt_errors(
        receipt, checksum=str(data.get("checksum", "")), require_resolved=require_resolved,
    )
    if errors:
        raise ValueError("invalid data protection receipt: " + "; ".join(errors))
    return dict(receipt)


def rollback_evidence_ingest(knowledge_root: Path, result: "IngestResult") -> bool:
    """Undo a newly-created Evidence+Queue pair while leaving Inbox retryable."""
    if result.reused:
        return False
    from .curation_queue import rollback_curation_work

    rollback_curation_work(knowledge_root, result.evidence_id)
    result.manifest_path.unlink(missing_ok=True)
    if result.original_path != result.manifest_path:
        result.original_path.unlink(missing_ok=True)
    return True


@dataclass(frozen=True)
class IngestResult:
    source_uuid: str
    original_path: Path
    manifest_path: Path
    evidence_id: str
    reused: bool = False


@dataclass(frozen=True)
class CaptureResult:
    intake_id: Optional[str]
    inbox_path: Optional[Path]
    checksum: str
    reused: bool = False
    evidence_id: Optional[str] = None
    evidence_path: Optional[Path] = None


class CaptureIdempotencyConflict(ValueError):
    """A safe, recoverable description of a changed capture retry."""

    def __init__(
        self,
        *,
        intake_id: Optional[str] = None,
        inbox_path: Optional[Path] = None,
        evidence_id: Optional[str] = None,
        evidence_path: Optional[Path] = None,
        existing_checksum: str,
        supplied_checksum: str,
    ) -> None:
        if bool(intake_id and inbox_path) == bool(evidence_id and evidence_path):
            raise ValueError("exactly one existing capture identity must be supplied")
        self.intake_id = intake_id
        self.inbox_path = inbox_path
        self.evidence_id = evidence_id
        self.evidence_path = evidence_path
        self.existing_checksum = existing_checksum
        self.supplied_checksum = supplied_checksum
        existing_kind = "intake" if intake_id else "evidence"
        existing_id = intake_id or evidence_id
        super().__init__(
            "idempotency_key already exists with a different checksum; "
            f"existing {existing_kind} is {existing_id}"
        )

    def as_dict(self, project_root: Path) -> Dict[str, object]:
        """Return recovery data without exposing captured source content."""
        payload = {
            "error": "idempotency_checksum_conflict",
            "stage": "inbox_capture",
            "message": str(self),
            "existing_checksum": self.existing_checksum,
            "supplied_checksum": self.supplied_checksum,
            "recovery": "Inspect the existing intake. Use a new source revision in the idempotency key only when the changed source is intentional.",
        }
        if self.intake_id and self.inbox_path:
            payload.update({
                "existing_intake_id": self.intake_id,
                "existing_inbox_path": self.inbox_path.resolve().relative_to(
                    project_root.resolve()
                ).as_posix(),
            })
        elif self.evidence_id and self.evidence_path:
            payload.update({
                "existing_evidence_id": self.evidence_id,
                "existing_evidence_path": self.evidence_path.resolve().relative_to(
                    project_root.resolve()
                ).as_posix(),
            })
            payload["recovery"] = (
                "Inspect the existing Evidence. Use a new source revision in the "
                "idempotency key only when the changed source is intentional."
            )
        return payload


INBOX_CONTENT_START = "<!-- INBOX_CONTENT_START -->"
INBOX_CONTENT_END = "<!-- INBOX_CONTENT_END -->"


def iter_active_inbox_items(knowledge_root: Path) -> Iterator[Path]:
    """Yield normal Inbox items, explicitly excluding every quarantine subtree.

    This exclusion is path-based rather than depth-based, so a future provider
    date hierarchy cannot cause quarantined originals to re-enter processing.
    """
    inbox_root = knowledge_root.resolve() / "inbox"
    if not inbox_root.is_dir():
        return
    for path in sorted(inbox_root.rglob("*.md")):
        if ".quarantine" not in path.relative_to(inbox_root).parts:
            yield path


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "evidence"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _content_checksum(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


@contextmanager
def _capture_idempotency_lock(
    knowledge_root: Path, provider: str, idempotency_key: str
) -> Iterator[None]:
    """Serialize one capture identity across local processes."""
    digest = hashlib.sha256(
        f"{provider}\0{idempotency_key}".encode("utf-8")
    ).hexdigest()
    lock_root = knowledge_root.resolve().parent / ".runtime" / "locks" / "capture"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{digest}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _synchronized_capture(function: Callable[..., CaptureResult]) -> Callable[..., CaptureResult]:
    """Hold the capture-key lock across lookup, conflict checking, and write."""
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(knowledge_root: Path, *args: Any, **kwargs: Any) -> CaptureResult:
        bound = signature.bind_partial(knowledge_root, *args, **kwargs)
        provider = str(bound.arguments.get("provider", ""))
        idempotency_key = bound.arguments.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return function(knowledge_root, *args, **kwargs)
        with _capture_idempotency_lock(
            knowledge_root, provider, idempotency_key.strip()
        ):
            return function(knowledge_root, *args, **kwargs)
    return wrapped


def _reuse_ingested_capture(
    knowledge_root: Path, provider: str, idempotency_key: str, checksum: str
) -> Optional[CaptureResult]:
    """Reuse or safely reject a capture key already preserved as Evidence."""
    evidence_root = knowledge_root.resolve() / "evidence"
    if not evidence_root.is_dir():
        return None
    for manifest_path in sorted(evidence_root.rglob("*.md")):
        if manifest_path.name in {"index.md", "log.md"}:
            continue
        try:
            document = parse_markdown(manifest_path)
        except (OSError, ValueError):
            continue
        data = document.frontmatter
        extensions = data.get("extensions", {})
        ingest = extensions.get("ingest", {}) if isinstance(extensions, dict) else {}
        if (
            data.get("type") != "evidence"
            or data.get("provider") != provider
            or not isinstance(ingest, dict)
            or ingest.get("idempotency_key") != idempotency_key
        ):
            continue
        existing_checksum = str(data.get("checksum", ""))
        if existing_checksum != checksum:
            raise CaptureIdempotencyConflict(
                evidence_id=str(data.get("id", "")),
                evidence_path=manifest_path,
                existing_checksum=existing_checksum,
                supplied_checksum=checksum,
            )
        original_path = evidence_original_path(document)
        if not original_path.is_file():
            raise ValueError("idempotent Evidence original is unavailable")
        return CaptureResult(
            None,
            None,
            checksum,
            True,
            evidence_id=str(data.get("id", "")),
            evidence_path=manifest_path,
        )
    return None


def read_conversation_intake(path: Path) -> tuple[Dict[str, object], object]:
    """Validate and return one self-contained conversation or document Inbox item."""
    document = parse_markdown(path)
    data = document.frontmatter
    if data.get("type") != "inbox_item" or data.get("content_type") not in {"conversation", "document", "file"}:
        raise ValueError("Inbox item content_type is invalid")
    for field in ("id", "title", "provider", "captured_at", "idempotency_key", "why_collected"):
        if not isinstance(data.get(field), str) or not str(data[field]).strip():
            raise ValueError(f"Inbox item {field} must be non-empty")
    if data.get("status") not in {"pending", "accepted"}:
        raise ValueError("Inbox item status is invalid")
    if data.get("sensitivity_review") not in {"completed", "required", "not_applicable"}:
        raise ValueError("Inbox item sensitivity_review is invalid")
    intended_use = data.get("intended_use")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("Inbox item intended_use must be a non-empty string array")
    if data.get("content_type") == "file":
        payload_name = data.get("payload_file")
        if not isinstance(payload_name, str) or not payload_name or Path(payload_name).name != payload_name:
            raise ValueError("Inbox file payload_file is invalid")
        payload_path = path.parent / payload_name
        if not payload_path.is_file():
            raise ValueError("Inbox file payload is missing")
        if _sha256(payload_path) != data.get("checksum"):
            raise ValueError("Inbox file checksum does not match payload")
        return data, payload_path
    start = document.body.find(INBOX_CONTENT_START)
    end = document.body.find(INBOX_CONTENT_END, start + len(INBOX_CONTENT_START))
    if start < 0 or end < 0:
        raise ValueError("Inbox item content markers are missing")
    content = document.body[start + len(INBOX_CONTENT_START):end]
    if not content.strip():
        raise ValueError("Inbox item content must be non-empty")
    if _content_checksum(content) != data.get("checksum"):
        raise ValueError("Inbox item checksum does not match content")
    provider = data.get("provider")
    if not isinstance(provider, str) or not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("Inbox item provider is invalid")
    if path.parent.name != provider:
        raise ValueError("Inbox item provider must match its source folder")
    return data, content


def accept_conversation_intake(
    knowledge_root: Path, intake_id: str, actor: str
) -> Dict[str, object]:
    """Apply the inspection gate to one valid pending conversation Inbox item."""
    if not isinstance(intake_id, str) or not intake_id.strip():
        raise ValueError("intake_id must be non-empty")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    knowledge_root = knowledge_root.resolve()
    for path in iter_active_inbox_items(knowledge_root):
        try:
            document = parse_markdown(path)
        except (OSError, ValueError):
            continue
        if document.frontmatter.get("id") != intake_id:
            continue
        data, _ = read_conversation_intake(path)
        return _accept_inbox_document(knowledge_root, path, document, data, actor)
    raise ValueError("intake_id must refer to an existing Inbox item")


def accept_ready_inbox(
    knowledge_root: Path, actor: str, *, limit: int = 100,
    intake_ids: Optional[set[str]] = None,
) -> Dict[str, object]:
    """Accept every pending Inbox item that already passes the inspection Gate.

    This bounded batch uses one Inbox traversal.  It never resolves sensitivity
    review or other blocking review work, which remains an explicit operation.
    """
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    knowledge_root = knowledge_root.resolve()
    accepted: List[Dict[str, object]] = []
    skipped: List[Dict[str, str]] = []
    for path in iter_active_inbox_items(knowledge_root):
        if len(accepted) >= limit:
            break
        try:
            document = parse_markdown(path)
            data, content = read_conversation_intake(path)
        except (FrontmatterError, OSError, ValueError):
            continue
        if intake_ids is not None and str(data.get("id")) not in intake_ids:
            continue
        if data.get("status") != "pending":
            continue
        try:
            accepted.append(_accept_inbox_document(knowledge_root, path, document, data, actor))
        except ValueError as error:
            skipped.append({
                "intake_id": str(data.get("id", "")),
                "reason": str(error),
            })
    return {
        "accepted_count": len(accepted), "skipped_count": len(skipped),
        "items": accepted, "skipped": skipped,
    }


def _accept_inbox_document(
    knowledge_root: Path, path: Path, document, data: Dict[str, object], actor: str,
) -> Dict[str, object]:
    """Validate and record one acceptance using an already located Inbox file."""
    intake_id = str(data.get("id", ""))
    _, candidate = read_conversation_intake(path)
    receipt_errors = data_protection_receipt_errors(
        data.get("data_protection_receipt"),
        checksum=str(data.get("checksum", "")),
        candidate_checksum=data_protection_candidate_checksum(data, candidate),
        require_resolved=True,
    )
    if receipt_errors:
        raise ValueError(
            "data protection review (sensitivity review) must be completed before acceptance: "
            + "; ".join(receipt_errors)
        )
    if not inbox_review_is_resolved(knowledge_root, intake_id):
        raise ValueError("inbox data protection requirements must be resolved before acceptance")
    if data.get("status") == "accepted":
        return {"intake_id": intake_id, "status": "accepted", "reused": True}
    if data.get("status") != "pending":
        raise ValueError("only pending Inbox items can be accepted")
    if data.get("sensitivity_review") == "required":
        raise ValueError("data protection review (sensitivity review) must be completed before acceptance")
    if has_blocking_inbox_review(knowledge_root, intake_id):
        raise ValueError("inbox data protection review (sensitivity review) must be resolved before acceptance")
    updated = dict(data)
    updated["status"] = "accepted"
    updated["inspection"] = {
        "actor": actor.strip(),
        "inspected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": [
            "required_metadata",
            "provider_folder",
            "content_checksum",
            "sensitivity_review",
        ],
    }
    path.write_text(render_markdown(updated, document.body), encoding="utf-8")
    advance_inbox_task(
        knowledge_root, intake_id=intake_id, stage="accepted", status="pending",
        actor=actor, next_action="ingest_accepted", outcome="accepted_inspection",
    )
    return {
        "intake_id": intake_id,
        "status": "accepted",
        "inbox_path": path.relative_to(knowledge_root.parent.resolve()).as_posix(),
        "reused": False,
    }


def run_automatic_pii_scan(knowledge_root: Path, intake_id: str) -> Dict[str, object]:
    """Scan and normalize the Inbox candidate before issuing its PII receipt.

    Capture uses the same redaction policy as an early safety guard.  This
    function is nevertheless authoritative for the Evidence transition: it
    rescans the actual Inbox candidate, updates its checksum when masking was
    needed, and only then records the receipt bound to that checksum.
    """
    knowledge_root = knowledge_root.resolve()
    # Validate the installation-local scanner switches before issuing the
    # canonical receipt. The active category set comes from the policy file.
    data_protection = load_data_protection_policy(knowledge_root.parent)
    for path in iter_active_inbox_items(knowledge_root):
        try:
            document = parse_markdown(path)
            data, content = read_conversation_intake(path)
        except (FrontmatterError, OSError, ValueError):
            continue
        if data.get("id") != intake_id:
            continue

        existing = data.get("pii_scan_receipt")
        candidate_fingerprint = data_protection_candidate_checksum(data, content)
        protection = data.get("data_protection_receipt")
        # A valid successful Receipt is the final PII decision for this exact
        # candidate, regardless of whether an Agent or a user created it.
        # Later workflow stages reuse it; only a changed checksum reopens PII.
        receipt_probe = {
            "checksum": data.get("checksum"),
            "extensions": {
                "pii_scan": existing,
                "pii_scanned": isinstance(existing, dict) and existing.get("result") in {"passed", "masked"},
                "pii_masked": isinstance(existing, dict) and existing.get("result") == "masked",
            },
        }
        if (
            isinstance(existing, dict)
            and existing.get("candidate_checksum") == candidate_fingerprint
            and not pii_scan_receipt_errors(receipt_probe)
        ):
            details = data.get("capture_details")
            precheck = details.get("sensitive_data_precheck") if isinstance(details, dict) else {}
            policy_categories = precheck.get("policy_categories", []) if isinstance(precheck, dict) else []
            return {
                "intake_id": intake_id, "pii_scan_receipt": existing, "reused": True,
                "policy_candidates": [
                    str(category) for category in policy_categories if isinstance(category, str)
                ],
            }

        # File payloads have no safe generic text representation.  Do not
        # claim they passed a text policy; retain them for an explicit review.
        if isinstance(content, Path):
            recorded = record_inbox_pii_scan_receipt(
                knowledge_root, intake_id, scanner="circled-wiki-pii-scan",
                scanner_version="pii-scan-v1", result="needs_review",
                reviewed_by="circled-wiki-pii-scan",
                receipt=f"runtime://pii-scan/{data['checksum']}",
            )
            return {**recorded, "policy_candidates": []}

        updated = dict(data)
        details = dict(data.get("capture_details", {})) if isinstance(data.get("capture_details"), dict) else {}
        prior_precheck = details.get("sensitive_data_precheck")
        prior_categories = (
            prior_precheck.get("categories", [])
            if isinstance(prior_precheck, dict) else []
        )
        prior_policy_categories = (
            prior_precheck.get("policy_categories", [])
            if isinstance(prior_precheck, dict) else []
        )
        content_scan = redact_sensitive_data(
            str(content), hard_mask_categories=data_protection.hard_mask_categories,
            disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
        )
        field_scans = {}
        for field in ("title", "why_collected", "source_url", "source_locator"):
            value = updated.get(field)
            if isinstance(value, str):
                field_scans[field] = redact_sensitive_data(
                    value, hard_mask_categories=data_protection.hard_mask_categories,
                    disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
                )
        intended_use = updated.get("intended_use")
        intended_use_scans = []
        if isinstance(intended_use, list):
            intended_use_scans = [
                redact_sensitive_data(
                    value, hard_mask_categories=data_protection.hard_mask_categories,
                    disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
                ) for value in intended_use if isinstance(value, str)
            ]

        masked_content = content_scan.content
        for field, scan in field_scans.items():
            updated[field] = scan.content
        if isinstance(intended_use, list):
            updated["intended_use"] = [
                scan.content if isinstance(value, str) else value
                for value, scan in zip(intended_use, intended_use_scans)
            ]
        categories = sorted({
            *[str(category) for category in prior_categories if isinstance(category, str)],
            *content_scan.categories,
            *(category for scan in field_scans.values() for category in scan.categories),
            *(category for scan in intended_use_scans for category in scan.categories),
        })
        policy_categories = sorted({
            *[str(category) for category in prior_policy_categories if isinstance(category, str)],
            *content_scan.policy_categories,
            *(category for scan in field_scans.values() for category in scan.policy_categories),
            *(category for scan in intended_use_scans for category in scan.policy_categories),
        })
        metadata_masked = any(
            updated.get(field) != data.get(field)
            for field in ("title", "why_collected", "source_url", "source_locator", "intended_use")
        )
        automatically_masked = bool(categories) or masked_content != content or metadata_masked
        details["sensitive_data_precheck"] = {
            "masked": automatically_masked, "categories": categories,
            "policy_categories": policy_categories,
        }
        updated["capture_details"] = details

        candidate_changed = (
            isinstance(protection, dict)
            and protection.get("candidate_checksum") != candidate_fingerprint
        ) or masked_content != content or any(
            updated.get(field) != data.get(field)
            for field in ("title", "why_collected", "source_url", "source_locator", "intended_use")
        )
        if candidate_changed:
            start = document.body.find(INBOX_CONTENT_START)
            end = document.body.find(INBOX_CONTENT_END, start + len(INBOX_CONTENT_START))
            body = (
                document.body[:start + len(INBOX_CONTENT_START)]
                + masked_content
                + document.body[end:]
            )
            updated["checksum"] = _content_checksum(masked_content)
            # A prior acceptance attests to an older candidate.  Re-run the
            # inexpensive inspection in this same reconciliation pass.
            if updated.get("status") == "accepted":
                updated["status"] = "pending"
                updated.pop("inspection", None)
            # The checksum change invalidates the prior sensitivity decision as
            # well as the PII projection.  Leave the Inbox explicitly requiring
            # the integrated Data Protection stage; otherwise an old resolved
            # sensitivity flag could bypass review on reprocessing.
            updated["sensitivity_review"] = "required"
            updated.pop("data_protection_receipt", None)
            updated.pop("sensitivity_inspection", None)
            updated.pop("pii_scan_receipt", None)
            path.write_text(render_markdown(updated, body), encoding="utf-8")
            reopen_inbox_data_protection_review(
                knowledge_root, intake_id=intake_id, actor="circled-wiki-pii-scan"
            )
            data = updated

        existing = data.get("pii_scan_receipt")
        result = "masked" if automatically_masked else "passed"
        if (
            isinstance(existing, dict)
            and existing.get("scanner") == "circled-wiki-pii-scan"
            and existing.get("scanner_version") == "pii-scan-v1"
            and existing.get("source_checksum") == data.get("checksum")
            and existing.get("candidate_checksum") == data_protection_candidate_checksum(data, content)
            and existing.get("result") == result
        ):
            return {
                "intake_id": intake_id, "pii_scan_receipt": existing, "reused": True,
                "policy_candidates": policy_categories,
            }
        recorded = record_inbox_pii_scan_receipt(
            knowledge_root, intake_id, scanner="circled-wiki-pii-scan",
            scanner_version="pii-scan-v1", result=result,
            reviewed_by="circled-wiki-pii-scan",
            receipt=f"runtime://pii-scan/{data['checksum']}",
        )
        return {**recorded, "policy_candidates": policy_categories}
    raise ValueError("intake_id must refer to an existing Inbox item")


def complete_inbox_sensitivity_review(
    knowledge_root: Path, intake_id: str, actor: str, decision: str, *,
    policy_ref: str, checks: List[str], matched_categories: List[str], rationale: str,
    data_protection_context: Optional[str] = None,
    _integrated: bool = False,
    _pii_scan: Optional[Dict[str, object]] = None,
    _agent_masked_findings: Optional[List[Dict[str, object]]] = None,
    _resolution: str = "no_policy_candidates",
) -> Dict[str, object]:
    """Record an actor-attributed sensitivity review before Inbox acceptance.

    Collection never asserts that a source is safe.  This distinct operation makes
    the reviewer and their explicit decision auditable before acceptance.
    """
    if not isinstance(intake_id, str) or not intake_id.strip():
        raise ValueError("intake_id must be non-empty")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    if decision not in {"completed", "not_applicable"}:
        raise ValueError("decision must be completed or not_applicable")
    if policy_ref != SENSITIVITY_POLICY_REF:
        raise ValueError(f"policy_ref must be {SENSITIVITY_POLICY_REF}")
    if not isinstance(checks, list) or set(checks) != SENSITIVITY_REQUIRED_CHECKS:
        raise ValueError("checks must contain the four inbox-sensitivity/v1 checks exactly once")
    if len(checks) != len(SENSITIVITY_REQUIRED_CHECKS):
        raise ValueError("checks must contain the four inbox-sensitivity/v1 checks exactly once")
    if not isinstance(matched_categories, list) or any(
        not isinstance(category, str) or not category.strip() for category in matched_categories
    ):
        raise ValueError("matched_categories must be a list of non-empty strings")
    if decision == "not_applicable" and matched_categories:
        raise ValueError("not_applicable requires matched_categories to be empty")
    if decision == "completed" and not matched_categories:
        raise ValueError("completed requires at least one matched category")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("rationale must be non-empty")
    knowledge_root = knowledge_root.resolve()
    data_protection = load_data_protection_policy(knowledge_root.parent)
    safe_matched_categories = [
        _safe_data_protection_text(category).strip() for category in matched_categories
    ]
    safe_rationale = _safe_data_protection_text(rationale, _agent_masked_findings)
    if not _integrated and any(
        category in data_protection.agent_mask_categories for category in matched_categories
    ):
        raise ValueError(
            "Agent mask categories require review-data-protection masking before resolution"
        )
    pii_scan = _pii_scan
    if pii_scan is None:
        pii_scan = run_automatic_pii_scan(knowledge_root, intake_id)["pii_scan_receipt"]
    for path in iter_active_inbox_items(knowledge_root):
        try:
            document = parse_markdown(path)
        except (OSError, ValueError):
            continue
        if document.frontmatter.get("id") != intake_id:
            continue
        data, content = read_conversation_intake(path)
        if data.get("status") != "pending":
            raise ValueError("only pending Inbox items can be sensitivity-reviewed")
        if data.get("sensitivity_review") != "required":
            existing_receipt = data.get("data_protection_receipt")
            existing_errors = data_protection_receipt_errors(
                existing_receipt,
                checksum=str(data.get("checksum", "")),
                candidate_checksum=data_protection_candidate_checksum(data, content),
                require_resolved=True,
            )
            if (
                existing_errors
                or not isinstance(existing_receipt, dict)
                or existing_receipt.get("sensitivity", {}).get("decision") != decision
            ):
                raise ValueError("Inbox sensitivity review is already resolved")
            for reason_code in ("sensitivity_review_required", "data_protection_required", "pii_scan_required", "pii_needs_review"):
                if reason_code == "pii_needs_review" and str(existing_receipt["pii_scan"].get("result")) == "needs_review":
                    continue
                resolve_inbox_review_requirement(
                    knowledge_root, intake_id=intake_id, reason_code=reason_code,
                    actor=actor.strip(), decision="data_protection_" + decision,
                    receipt=str(existing_receipt["receipt"]),
                )
            return {
                "intake_id": intake_id, "sensitivity_review": decision,
                "status": str(data.get("status", "pending")),
                "review_status": "reprocessing" if inbox_review_is_resolved(knowledge_root, intake_id) else "awaiting_user",
            }
        policy_candidates = () if _integrated else _policy_candidates_for_inbox(
            data, content, hard_mask_categories=data_protection.hard_mask_categories,
            disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
        )
        if policy_candidates:
            raise ValueError(
                "residual PII candidate requires review-data-protection before resolution"
            )
        unified_receipt = _write_data_protection_receipt(
            path, pii_scan=pii_scan, policy=data_protection, actor=actor,
            sensitivity_decision=decision, context=data_protection_context or "",
            matched_categories=safe_matched_categories,
            agent_masked_findings=_agent_masked_findings or [],
            resolution=_resolution, rationale=safe_rationale,
        )
        review = resolve_inbox_review_requirement(
            knowledge_root, intake_id=intake_id,
            reason_code="sensitivity_review_required", actor=actor.strip(),
            decision=decision, receipt=f"inbox-review://sensitivity/{intake_id.rsplit('/', 1)[-1]}",
        )
        for reason_code in ("data_protection_required", "pii_scan_required", "pii_needs_review"):
            if reason_code == "pii_needs_review" and str(pii_scan.get("result")) == "needs_review":
                continue
            review = resolve_inbox_review_requirement(
                knowledge_root, intake_id=intake_id, reason_code=reason_code,
                actor=actor.strip(), decision="data_protection_" + decision,
                receipt=str(unified_receipt["receipt"]),
            )
        return {
            "intake_id": intake_id, "sensitivity_review": decision,
            "status": "pending", "review_status": review["status"],
        }
    raise ValueError("intake_id must refer to an existing Inbox item")


def review_data_protection(
    knowledge_root: Path, intake_id: str, actor: str, *, context: str,
    checks: List[str], rationale: str, findings: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, object]:
    """Apply Agent-identified sensitive-data masking, then complete the review.

    ``findings`` are transient Agent observations: each supplies an exact text
    fragment and a configured Agent mask category.  The fragment is replaced in
    the Inbox and never copied to the review receipt.
    """
    knowledge_root = knowledge_root.resolve()
    policy = load_data_protection_policy(knowledge_root.parent)
    if not isinstance(context, str):
        raise ValueError("context must be a string")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("rationale must be non-empty")
    findings = _validate_sensitivity_findings(policy, findings)
    safe_rationale = _safe_data_protection_text(rationale, findings)
    safe_context = context.strip() if context.strip() in policy.agent_mask_categories else ""
    # The integrated procedure always starts with the canonical hard PII Scan.
    # Agent masking only removes exact text from that candidate, so the same
    # deterministic scan result can be rebound to the final candidate without
    # re-running the scanner.
    scan = run_automatic_pii_scan(knowledge_root, intake_id)
    for path in iter_active_inbox_items(knowledge_root):
        try:
            document = parse_markdown(path)
            data, content = read_conversation_intake(path)
        except (OSError, ValueError):
            continue
        if data.get("id") != intake_id:
            continue
        if findings:
            if not isinstance(content, str):
                raise ValueError("Agent sensitivity masking requires text Inbox content")
            metadata, masked_content, finding_summary, candidate_changed = (
                _mask_sensitivity_findings_in_candidate(data, content, findings)
            )
            if not candidate_changed or any(
                int(item.get("count", 0)) < 1 for item in finding_summary
            ):
                raise ValueError("Agent sensitivity findings did not match Inbox candidate")
            metadata["checksum"] = _content_checksum(masked_content)
            metadata.pop("pii_scan_receipt", None)
            start = document.body.find(INBOX_CONTENT_START)
            end = document.body.find(INBOX_CONTENT_END, start + len(INBOX_CONTENT_START))
            body = (
                document.body[:start + len(INBOX_CONTENT_START)]
                + masked_content
                + document.body[end:]
            )
            path.write_text(render_markdown(metadata, body), encoding="utf-8")
            document = parse_markdown(path)
            data, content = read_conversation_intake(path)
            # Sensitivity masking is subtractive: it cannot introduce a new
            # machine-detectable PII value.  Preserve the single PII scan and
            # bind its compatibility receipt to the final candidate instead of
            # performing an identical second scan.
            rebound_scan = dict(scan["pii_scan_receipt"])
            rebound_scan.update({
                "source_checksum": str(data["checksum"]),
                "candidate_checksum": data_protection_candidate_checksum(data, content),
                "receipt": f"runtime://pii-scan/{data['checksum']}",
            })
            scan = {
                "intake_id": intake_id, "pii_scan_receipt": rebound_scan, "reused": True,
                "policy_candidates": scan.get("policy_candidates", []),
            }
        else:
            finding_summary = []
        # The deterministic PII scan above also returned its residual policy
        # candidates.  Do not walk the candidate through a second scanner just
        # to feed the Agent sensitivity decision.
        detected = tuple(scan.get("policy_candidates", ()))
        resolution = resolve_policy_context(policy, detected, context)
        # Once the Agent has supplied and masked an exact finding for its
        # selected target, unrelated residual contact data (for example an
        # email beside a customer phone) is not a new preservation decision.
        if resolution == "awaiting_user" and any(
            item.get("category") == context for item in finding_summary
            if isinstance(item, dict)
        ):
            resolution = "no_mask_target"
        pii_result = str(scan["pii_scan_receipt"].get("result", ""))
        if resolution == "awaiting_user" or pii_result == "needs_review":
            pending_categories = sorted({
                *[str(category) for category in detected],
                *[str(item["category"]) for item in finding_summary if isinstance(item, dict) and "category" in item],
            })
            _write_data_protection_receipt(
                path, pii_scan=scan["pii_scan_receipt"], policy=policy, actor=actor,
                sensitivity_decision="awaiting_user", context=context,
                matched_categories=pending_categories,
                agent_masked_findings=finding_summary, resolution=(
                    resolution if resolution == "awaiting_user" else "pii_needs_review"
                ), rationale=safe_rationale,
            )
            escalation = request_inbox_sensitivity_decision(
                knowledge_root, intake_id, actor,
                question=(
                    "PII Scan 후 Agent 마스킹 대상과 정확한 범위를 판단할 수 있는가?"
                    if resolution == "awaiting_user" else
                    "PII Scan needs_review 결과에 대한 안전 처리를 승인할 수 있는가?"
                ),
                missing_procedure=(
                    "Agent 마스킹 대상과 정확한 범위가 확인되지 않았다."
                    if resolution == "awaiting_user" else
                    "PII 후보의 안전 처리 방식이 확인되지 않았다."
                ),
                safe_next_action="안전 처리와 보존 범위를 확인한 뒤 review-data-protection을 재실행한다.",
                facts=[
                    "정책/PII 검토 범주: " + ", ".join(pending_categories or ("확인 불가",)),
                ],
                hypotheses=[],
            )
            return {
                **escalation,
                "review_status": "awaiting_user",
                "data_protection": {
                    "hard_scan_result": pii_result,
                    "policy_candidates": list(detected),
                    "agent_masked_findings": finding_summary,
                    "context": safe_context,
                    "resolution": resolution,
                },
            }
        matched = sorted({
            *([context] if detected and context else []),
            *[str(item["category"]) for item in finding_summary if isinstance(item, dict) and "category" in item],
        })
        decision = "completed" if matched else "not_applicable"
        review = complete_inbox_sensitivity_review(
            knowledge_root, intake_id, actor, decision, policy_ref=policy.policy_ref,
            checks=checks, matched_categories=matched, rationale=safe_rationale,
            data_protection_context=context,
            _integrated=True, _pii_scan=scan["pii_scan_receipt"],
            _agent_masked_findings=finding_summary, _resolution=resolution,
        )
        return {
            **review,
            "data_protection": {
                "hard_scan_result": pii_result,
                "policy_candidates": list(detected),
                "agent_masked_findings": finding_summary,
                "context": safe_context,
                "resolution": resolution,
            },
        }
    raise ValueError("intake_id must refer to an existing Inbox item")


def _validate_sensitivity_findings(
    policy, findings: Optional[List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    if findings is None:
        return []
    if not isinstance(findings, list):
        raise ValueError("findings must be a list")
    validated = []
    seen_values = set()
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("each finding must be an object")
        category = finding.get("category")
        value = finding.get("value")
        if category not in policy.agent_mask_categories:
            raise ValueError("finding category must be a configured agent mask category")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("finding value must be a non-empty string")
        if value in seen_values:
            raise ValueError("finding values must be unique")
        seen_values.add(value)
        validated.append({"category": category, "value": value})
    return validated


def _mask_sensitivity_findings_in_candidate(
    data: Dict[str, object], content: str, findings: List[Dict[str, str]],
) -> tuple[Dict[str, object], str, List[Dict[str, object]], bool]:
    """Mask Agent findings in body and metadata that will enter Evidence."""
    metadata = dict(data)
    masked_content = content
    summary: List[Dict[str, object]] = []
    changed = False
    for finding in findings:
        value = finding["value"]
        count = masked_content.count(value)
        masked_content = masked_content.replace(value, REDACTED_VALUE)
        for field in ("title", "why_collected", "source_url", "source_locator"):
            field_value = metadata.get(field)
            if isinstance(field_value, str):
                field_count = field_value.count(value)
                if field_count:
                    metadata[field] = field_value.replace(value, REDACTED_VALUE)
                    count += field_count
        intended_use = metadata.get("intended_use")
        if isinstance(intended_use, list):
            masked_use = []
            for item in intended_use:
                if isinstance(item, str):
                    item_count = item.count(value)
                    if item_count:
                        item = item.replace(value, REDACTED_VALUE)
                        count += item_count
                masked_use.append(item)
            metadata["intended_use"] = masked_use
        if count:
            changed = True
        summary.append({"category": finding["category"], "count": count})
    return metadata, masked_content, summary, changed


def _policy_candidates_for_inbox(
    data: Dict[str, object], content: object, *,
    hard_mask_categories: Optional[Iterable[str]] = None,
    disabled_hard_mask_categories: Optional[Iterable[str]] = None,
) -> tuple[str, ...]:
    """Collect residual scanner candidates from body and copied metadata.

    Hard-mask switches are applied by the canonical PII Scan before this
    function is called.  Anything the scanner still recognizes is therefore
    sent to the integrated sensitivity review; no second policy allowlist is
    needed to route it.
    """
    values: List[str] = []
    if isinstance(content, str):
        values.append(content)
    for field in ("title", "why_collected", "source_url", "source_locator"):
        value = data.get(field)
        if isinstance(value, str):
            values.append(value)
    intended_use = data.get("intended_use")
    if isinstance(intended_use, list):
        values.extend(value for value in intended_use if isinstance(value, str))
    return tuple(sorted({
        category
        for value in values
        for category in redact_sensitive_data(
            value, hard_mask_categories=hard_mask_categories,
            disabled_hard_mask_categories=disabled_hard_mask_categories,
        ).policy_categories
    }))


def request_inbox_sensitivity_decision(
    knowledge_root: Path, intake_id: str, actor: str, *, question: str,
    missing_procedure: str, safe_next_action: str, facts: List[str],
    hypotheses: List[str],
) -> Dict[str, object]:
    """Keep the Inbox pending and record why only the user can decide next."""
    from .pii import build_pii_scan_receipt

    values = {
        "question": question, "missing_procedure": missing_procedure,
        "safe_next_action": safe_next_action,
    }
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError("sensitivity escalation fields must be non-empty strings")
    if any(
        not isinstance(items, list) or any(
            not isinstance(value, str) or not value.strip() for value in items
        ) for items in (facts, hypotheses)
    ):
        raise ValueError("facts and hypotheses must be lists of non-empty strings")

    def mask(value: str):
        return redact_sensitive_data(value, mask_policy_categories=True)

    question_scan = mask(question)
    procedure_scan = mask(missing_procedure)
    action_scan = mask(safe_next_action)
    fact_scans = [mask(value) for value in facts]
    hypothesis_scans = [mask(value) for value in hypotheses]
    raw_values = [question, missing_procedure, safe_next_action, *facts, *hypotheses]
    categories = sorted({
        *question_scan.categories, *procedure_scan.categories, *action_scan.categories,
        *(category for scan in [*fact_scans, *hypothesis_scans] for category in scan.categories),
    })
    policy_categories = sorted({
        *question_scan.policy_categories, *procedure_scan.policy_categories,
        *action_scan.policy_categories,
        *(category for scan in [*fact_scans, *hypothesis_scans]
          for category in scan.policy_categories),
    })
    task_checksum = _content_checksum("\n".join(raw_values))
    pii_scan_receipt = build_pii_scan_receipt(
        task_checksum, scanner="circled-wiki-pii-scan", scanner_version="pii-scan-v1",
        result="masked" if categories else "passed", reviewed_by="circled-wiki-pii-scan",
        receipt=f"runtime://pii-scan/task/{task_checksum}",
    )
    for path in iter_active_inbox_items(knowledge_root):
        try:
            data, _ = read_conversation_intake(path)
        except (FrontmatterError, OSError, ValueError):
            continue
        if data.get("id") != intake_id:
            continue
        if data.get("status") != "pending" or data.get("sensitivity_review") != "required":
            raise ValueError("only required pending sensitivity reviews can await user")
        return escalate_inbox_sensitivity_review(
            knowledge_root, intake_id=intake_id, actor=actor, question=question_scan.content,
            missing_procedure=procedure_scan.content, safe_next_action=action_scan.content,
            facts=[scan.content for scan in fact_scans],
            hypotheses=[scan.content for scan in hypothesis_scans],
            pii_scan_receipt={
                **pii_scan_receipt,
                "categories": categories,
                "policy_candidates": policy_categories,
            },
        )
    raise ValueError("intake_id must refer to an existing Inbox item")


def record_inbox_pii_scan_receipt(
    knowledge_root: Path, intake_id: str, *, scanner: str, scanner_version: str,
    result: str, reviewed_by: str, receipt: str, scanned_at: Optional[str] = None,
) -> Dict[str, object]:
    """Attach an external PII result as input to the integrated review.

    This compatibility path never resolves an already-completed sensitivity
    decision; it reopens Data Protection so the final unified Receipt is
    produced by ``review_data_protection``.
    """
    from .pii import build_pii_scan_receipt

    for path in iter_active_inbox_items(knowledge_root):
        try:
            data, content = read_conversation_intake(path)
        except (FrontmatterError, OSError, ValueError):
            continue
        if data.get("id") != intake_id:
            continue
        updated = dict(data)
        scan = build_pii_scan_receipt(
            str(data.get("checksum", "")), scanner=scanner,
            scanner_version=scanner_version, result=result,
            reviewed_by=reviewed_by,
            receipt=_safe_data_protection_text(receipt), scanned_at=scanned_at,
            candidate_checksum=data_protection_candidate_checksum(data, content),
        )
        updated["pii_scan_receipt"] = scan
        reopened = updated.get("sensitivity_review") != "required"
        if reopened:
            # A low-level external scan is only an input to the integrated
            # procedure.  It must not refine an already-resolved sensitivity
            # decision into a new final Receipt without re-running the Agent
            # Data Protection stage on the same candidate.
            updated["sensitivity_review"] = "required"
            updated.pop("data_protection_receipt", None)
            updated.pop("sensitivity_inspection", None)
            if updated.get("status") == "accepted":
                updated["status"] = "pending"
                updated.pop("inspection", None)
        document = parse_markdown(path)
        path.write_text(render_markdown(updated, document.body), encoding="utf-8")
        if reopened:
            reopened_review = reopen_inbox_data_protection_review(
                knowledge_root, intake_id=intake_id, actor=reviewed_by,
            )
            if reopened_review.get("status") == "no_review":
                enqueue_inbox_review(
                    knowledge_root, intake_id=intake_id, inbox_path=path,
                    current_stage="sensitivity_review", reason_code="sensitivity_review_required",
                )
            if result == "needs_review":
                queue = enqueue_inbox_review(
                    knowledge_root, intake_id=intake_id, inbox_path=path,
                    current_stage="data_protection", reason_code="pii_needs_review",
                )
                return {"intake_id": intake_id, "pii_scan_receipt": scan, "review_queue": queue}
            return {
                "intake_id": intake_id, "pii_scan_receipt": scan,
                "review_status": "reprocessing",
            }
        if result == "needs_review":
            queue = enqueue_inbox_review(
                knowledge_root, intake_id=intake_id, inbox_path=path,
                current_stage="data_protection",
                reason_code="pii_needs_review",
            )
            return {"intake_id": intake_id, "pii_scan_receipt": scan, "review_queue": queue}
        review = {"status": "no_review"}
        for reason_code in ("pii_needs_review", "pii_scan_required"):
            resolved = resolve_inbox_review_requirement(
                knowledge_root, intake_id=intake_id,
                reason_code=reason_code, actor=reviewed_by,
                decision=f"pii_scan_{result}", receipt=receipt,
            )
            if resolved["status"] != "no_review":
                review = resolved
        return {"intake_id": intake_id, "pii_scan_receipt": scan, "review_status": review["status"]}
    raise ValueError("intake_id must refer to an existing Inbox item")


def ingest_evidence(
    knowledge_root: Path,
    source_path: Path,
    provider: str,
    *,
    why_collected: str,
    intended_use: List[str],
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    source_locator: Optional[str] = None,
    source_external_id: Optional[str] = None,
    captured_from: str = "manual",
    captured_at: Optional[datetime] = None,
    reuse_value: str = "medium",
    retention_class: str = "general_reference",
    sensitivity_review: str = "required",
    idempotency_key: Optional[str] = None,
    content_mode: str = "external_file",
    capture_fidelity: Optional[str] = None,
    pii_scanned: bool = False,
    pii_scan_receipt: Optional[Dict[str, object]] = None,
    data_protection_receipt: Optional[Dict[str, object]] = None,
    inbox_review: Optional[Dict[str, object]] = None,
    capture_details: Optional[Dict[str, object]] = None,
    original_stem: Optional[str] = None,
) -> IngestResult:
    """Move an inbox original through `.raw` and preserve it as new Evidence.

    Only originals up to 10 MiB are handled in this local Git-backed MVP. Oversized
    originals remain in `.raw` so an operator can place them in approved external
    storage and create a manifest with `extensions.storage.class: external`.
    """
    knowledge_root = knowledge_root.resolve()
    inbox_root = (knowledge_root / "inbox").resolve()
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"inbox file does not exist: {source_path}")
    if inbox_root not in source_path.parents:
        raise ValueError("source_path must be inside knowledge/inbox/")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("provider must contain only lowercase letters, digits, underscores, or hyphens")
    if captured_from not in {"api", "webhook", "manual", "upload", "sync"}:
        raise ValueError("captured_from is invalid")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if reuse_value not in {"high", "medium", "low"}:
        raise ValueError("reuse_value is invalid")
    if retention_class not in {
        "workflow_reference", "decision_record", "outcome", "general_reference", "ephemeral"
    }:
        raise ValueError("retention_class is invalid")
    if sensitivity_review not in {"completed", "required", "not_applicable"}:
        raise ValueError("sensitivity_review is invalid")
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or len(idempotency_key) > 200
    ):
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
    if source_external_id is not None and (
        not isinstance(source_external_id, str) or not source_external_id.strip()
    ):
        raise ValueError("source_external_id must be a non-empty string when supplied")
    if content_mode not in {"external_file", "embedded"}:
        raise ValueError("content_mode must be external_file or embedded")
    if content_mode == "embedded":
        if source_path.suffix.lower() != ".md":
            raise ValueError("embedded Evidence source must be a Markdown file")
        try:
            with source_path.open(encoding="utf-8", newline="") as source_file:
                source_file.read()
        except UnicodeDecodeError as error:
            raise ValueError("embedded Evidence source must be valid UTF-8") from error
    if not isinstance(pii_scanned, bool):
        raise ValueError("pii_scanned must be boolean")
    if pii_scanned:
        raise ValueError("pii_scanned cannot be set directly; supply pii_scan_receipt")
    if capture_details is not None and not isinstance(capture_details, dict):
        raise ValueError("capture_details must be an object")
    organization_id = require_stable_organization_id(knowledge_root)
    source_checksum = _sha256(source_path)
    if data_protection_receipt is not None:
        errors = data_protection_receipt_errors(
            data_protection_receipt, checksum=source_checksum, require_resolved=True,
        )
        if errors:
            raise ValueError("invalid data protection receipt: " + "; ".join(errors))
        if pii_scan_receipt is None:
            pii_scan_receipt = dict(data_protection_receipt["pii_scan"])
    if pii_scan_receipt is not None:
        receipt = dict(pii_scan_receipt)
        receipt_result = receipt.get("result")
        receipt_probe = {
            "checksum": source_checksum,
            "extensions": {
                "pii_scan": receipt,
                "pii_scanned": receipt_result in {"passed", "masked"},
                "pii_masked": receipt_result == "masked",
            },
        }
        from .pii import pii_scan_receipt_errors

        errors = pii_scan_receipt_errors(receipt_probe)
        if errors:
            raise ValueError(
                "invalid pre-creation PII scan receipt: " + "; ".join(errors)
            )
        if receipt_result == "needs_review":
            raise ValueError(
                "PII scan requires review; keep the source in Inbox until a passed or masked receipt is available"
            )
    if idempotency_key is not None:
        for manifest_path in sorted((knowledge_root / "evidence").rglob("*.md")):
            if manifest_path.name in {"index.md", "log.md"}:
                continue
            document = parse_markdown(manifest_path)
            extensions = document.frontmatter.get("extensions", {})
            ingest = extensions.get("ingest", {}) if isinstance(extensions, dict) else {}
            if (
                document.frontmatter.get("provider") != provider
                or not isinstance(ingest, dict)
                or ingest.get("idempotency_key") != idempotency_key
            ):
                continue
            if document.frontmatter.get("checksum") != source_checksum:
                raise ValueError("idempotency_key already exists with a different checksum")
            original_path = evidence_original_path(document)
            if not original_path.is_file():
                raise ValueError("idempotent Evidence original is unavailable")
            source_path.unlink()
            return IngestResult(
                str(document.frontmatter["source_uuid"]), original_path, manifest_path,
                str(document.frontmatter["id"]), True,
            )

    source_uuid = str(uuid4())
    raw_root = knowledge_root / ".raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    source_stem = _slug(original_stem or source_path.stem)
    raw_path = raw_root / f"{source_stem}_{source_uuid}{source_path.suffix.lower()}"
    shutil.move(str(source_path), str(raw_path))

    if raw_path.stat().st_size > MAX_GIT_EVIDENCE_BYTES:
        raise ValueError(
            "original is larger than 10 MiB and remains in knowledge/.raw/; "
            "store it externally before creating its manifest"
        )

    now = captured_at or datetime.now(timezone.utc)
    date_path = now.strftime("%Y/%m/%d")
    name = source_stem
    evidence_root = knowledge_root / "evidence" / provider / date_path
    evidence_root.mkdir(parents=True, exist_ok=True)
    original_name = f"{name}_{source_uuid}{raw_path.suffix.lower()}"
    manifest_name = f"{name}_{source_uuid}.md"
    if original_name == manifest_name:
        original_name += ".original"
    original_path = evidence_root / original_name
    manifest_path = evidence_root / manifest_name
    evidence_id = f"evidence/{organization_id}/{manifest_path.name}"
    timestamp = now.isoformat(timespec="seconds")
    source_ref = {
        "provider": provider,
        "provider_url": source_url or "",
        "captured_from": captured_from,
        "snapshot_at": timestamp,
    }
    if source_locator:
        source_ref["locator"] = source_locator
    if source_external_id:
        source_ref["external_id"] = source_external_id.strip()
    frontmatter = {
        "type": "evidence",
        "id": evidence_id,
        "tags": ["evidence", provider, "source"],
        "title": title or source_path.stem,
        "source_uuid": source_uuid,
        "provider": provider,
        "source_ref": source_ref,
        "captured_at": timestamp,
        "checksum": source_checksum,
        "language": "ko",
        "original_file_git_tracked": True,
        "derived_files": [],
        "extensions": {
            "availability": "available",
            "capture_context": {
                "why_collected": why_collected.strip(),
                "intended_use": [item.strip() for item in intended_use],
                "reuse_value": reuse_value,
                "retention_class": retention_class,
                "sensitivity_review": sensitivity_review,
            },
            "visibility": "internal",
            "pii_scanned": pii_scanned,
            "pii_masked": False,
            "storage": {"class": "git"},
            "ingest": {"idempotency_key": idempotency_key} if idempotency_key else {},
        },
    }
    if pii_scan_receipt is not None:
        receipt = dict(pii_scan_receipt)
        frontmatter["extensions"]["pii_scan"] = receipt
        frontmatter["extensions"]["pii_scanned"] = receipt.get("result") in {"passed", "masked"}
        frontmatter["extensions"]["pii_masked"] = receipt.get("result") == "masked"
    if data_protection_receipt is not None:
        frontmatter["extensions"]["data_protection_receipt"] = dict(data_protection_receipt)
    if inbox_review is not None:
        frontmatter["extensions"]["inbox_review"] = dict(inbox_review)
    if content_mode == "embedded":
        frontmatter["extensions"]["content_mode"] = "embedded"
        frontmatter["extensions"]["checksum_scope"] = "document_body"
        frontmatter["extensions"]["embedded_format_version"] = EMBEDDED_FORMAT_VERSION
        frontmatter["extensions"]["capture_fidelity"] = capture_fidelity or "verbatim"
        if capture_details:
            frontmatter["extensions"]["conversation_capture"] = capture_details
        with raw_path.open(encoding="utf-8", newline="") as source_file:
            embedded_content = source_file.read()
        # Do not pass the original through render_markdown: it trims leading
        # whitespace, while the complete body is the checksum-covered original.
        with manifest_path.open("w", encoding="utf-8", newline="") as manifest_file:
            manifest_file.write(render_markdown(frontmatter))
            manifest_file.write(render_embedded_body(embedded_content))
        original_path = manifest_path
    else:
        frontmatter["original_file"] = original_name
        frontmatter["extensions"]["content_mode"] = "external_file"
        frontmatter["extensions"]["checksum_scope"] = "original_file"
        manifest_path.write_text(
            render_markdown(frontmatter, "# Summary\n\nPending curation.\n"), encoding="utf-8"
        )
        shutil.move(str(raw_path), str(original_path))
    validation = validate_document(manifest_path, knowledge_root)
    if not validation.is_valid:
        manifest_path.unlink(missing_ok=True)
        if content_mode == "external_file" and original_path.is_file():
            shutil.move(str(original_path), str(raw_path))
        errors = validation.okf_errors + validation.profile_errors
        raise ValueError(
            "manifest validation failed: "
            + "; ".join(errors or ["validator returned no diagnostic details"])
        )
    try:
        from .curation_queue import enqueue_curation_work

        enqueue_curation_work(knowledge_root, evidence_id, manifest_path)
    except Exception:
        manifest_path.unlink(missing_ok=True)
        if content_mode == "external_file" and original_path.is_file():
            shutil.move(str(original_path), str(raw_path))
        raise
    if content_mode == "embedded":
        raw_path.unlink(missing_ok=True)
    return IngestResult(source_uuid, original_path, manifest_path, evidence_id)


@_synchronized_capture
def capture_conversation(
    knowledge_root: Path,
    content: str,
    provider: str,
    *,
    title: str,
    why_collected: str,
    intended_use: List[str],
    idempotency_key: str,
    thread_ref: Optional[str] = None,
    turn_from: Optional[int] = None,
    turn_to: Optional[int] = None,
    artifacts: Optional[List[Dict[str, object]]] = None,
    captured_at: Optional[datetime] = None,
) -> CaptureResult:
    """Land a conversation in its provider Inbox without ingesting or curating it."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("conversation content must be non-empty")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError(
            "provider must contain only lowercase letters, digits, underscores, or hyphens"
        )
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be non-empty")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if turn_from is not None and (isinstance(turn_from, bool) or turn_from < 0):
        raise ValueError("turn_from must be a non-negative integer")
    if turn_to is not None and (isinstance(turn_to, bool) or turn_to < 0):
        raise ValueError("turn_to must be a non-negative integer")
    if turn_from is not None and turn_to is not None and turn_to < turn_from:
        raise ValueError("turn_to must be greater than or equal to turn_from")
    if artifacts is not None and (
        not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts)
    ):
        raise ValueError("artifacts must be an array of objects")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")

    data_protection = load_data_protection_policy(knowledge_root.resolve().parent)
    content_precheck = redact_sensitive_data(
        content, hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    title_precheck = redact_sensitive_data(
        title, hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    reason_precheck = redact_sensitive_data(
        why_collected, hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    content = content_precheck.content
    title = title_precheck.content
    why_collected = reason_precheck.content
    masked_categories = sorted(set(
        content_precheck.categories + title_precheck.categories + reason_precheck.categories
    ))
    policy_categories = sorted(set(
        content_precheck.policy_categories + title_precheck.policy_categories
        + reason_precheck.policy_categories
    ))

    organization_id = require_stable_organization_id(knowledge_root)
    checksum = _content_checksum(content)
    ingested = _reuse_ingested_capture(
        knowledge_root, provider, idempotency_key.strip(), checksum
    )
    if ingested:
        return ingested
    inbox_root = knowledge_root.resolve() / "inbox" / provider
    inbox_root.mkdir(parents=True, exist_ok=True)
    for existing_path in sorted(inbox_root.glob("*.md")):
        try:
            existing, _ = read_conversation_intake(existing_path)
        except (OSError, ValueError):
            continue
        if existing.get("idempotency_key") != idempotency_key:
            continue
        if existing.get("checksum") != checksum:
            raise CaptureIdempotencyConflict(
                intake_id=str(existing["id"]),
                inbox_path=existing_path,
                existing_checksum=str(existing["checksum"]),
                supplied_checksum=checksum,
            )
        return CaptureResult(
            str(existing["id"]), existing_path, checksum, True
        )

    intake_uuid = str(uuid4())
    capture_path = inbox_root / f"{_slug(title)}-{intake_uuid}.md"
    details: Dict[str, object] = {"capture_type": "conversation"}
    if thread_ref:
        details["thread_ref"] = thread_ref
    if turn_from is not None:
        details["turn_from"] = turn_from
    if turn_to is not None:
        details["turn_to"] = turn_to
    if artifacts:
        details["artifacts"] = artifacts
    if masked_categories or policy_categories:
        details["sensitive_data_precheck"] = {
            "masked": bool(masked_categories),
            "categories": masked_categories,
            "policy_categories": policy_categories,
        }
    now = captured_at or datetime.now(timezone.utc)
    intake_id = f"inbox://{organization_id}/{provider}/{intake_uuid}"
    frontmatter = {
        "type": "inbox_item",
        "id": intake_id,
        "title": title.strip(),
        "provider": provider,
        "content_type": "conversation",
        "captured_at": now.isoformat(timespec="seconds"),
        "status": "pending",
        "checksum": checksum,
        "idempotency_key": idempotency_key.strip(),
        "why_collected": why_collected.strip(),
        "intended_use": [item.strip() for item in intended_use],
        "sensitivity_review": "required",
        "capture_details": details,
    }
    capture_path.write_text(
        render_markdown(
            frontmatter,
            "# Inbox Conversation\n\n"
            f"{INBOX_CONTENT_START}{content}{INBOX_CONTENT_END}\n",
        ),
        encoding="utf-8",
    )
    ensure_inbox_task(knowledge_root, intake_id=intake_id, inbox_path=capture_path)
    enqueue_inbox_review(
        knowledge_root, intake_id=intake_id, inbox_path=capture_path,
        current_stage="sensitivity_review",
        reason_code="sensitivity_review_required",
    )
    return CaptureResult(intake_id, capture_path, checksum)


@_synchronized_capture
def capture_document(
    knowledge_root: Path,
    content: str,
    provider: str,
    *,
    title: str,
    why_collected: str,
    intended_use: List[str],
    idempotency_key: str,
    source_url: Optional[str] = None,
    source_locator: Optional[str] = None,
    captured_from: str = "sync",
    captured_at: Optional[datetime] = None,
    capture_details: Optional[Dict[str, object]] = None,
) -> CaptureResult:
    """Land an external document as an Inbox Item with source_ref, without ingesting it."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("document content must be non-empty")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("provider must contain only lowercase letters, digits, underscores, or hyphens")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be non-empty")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if captured_from not in {"api", "webhook", "manual", "upload", "sync"}:
        raise ValueError("captured_from is invalid")
    if capture_details is not None and not isinstance(capture_details, dict):
        raise ValueError("capture_details must be an object")
    source_external_id = capture_details.get("external_id") if isinstance(capture_details, dict) else None
    if source_external_id is not None and (not isinstance(source_external_id, str) or not source_external_id.strip() or len(source_external_id) > 200):
        raise ValueError("capture_details.external_id must be a non-empty string up to 200 characters")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
    data_protection = load_data_protection_policy(knowledge_root.resolve().parent)
    content_precheck = redact_sensitive_data(
        content, hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    title_precheck = redact_sensitive_data(
        title, hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    reason_precheck = redact_sensitive_data(
        why_collected, hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    url_precheck = redact_sensitive_data(
        source_url or "", hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    locator_precheck = redact_sensitive_data(
        source_locator or "", hard_mask_categories=data_protection.hard_mask_categories,
        disabled_hard_mask_categories=data_protection.disabled_hard_mask_categories,
    )
    content = content_precheck.content
    title = title_precheck.content
    why_collected = reason_precheck.content
    source_url = url_precheck.content
    source_locator = locator_precheck.content
    masked_categories = sorted(set(
        content_precheck.categories + title_precheck.categories + reason_precheck.categories
        + url_precheck.categories + locator_precheck.categories
    ))
    policy_categories = sorted(set(
        content_precheck.policy_categories + title_precheck.policy_categories
        + reason_precheck.policy_categories + url_precheck.policy_categories
        + locator_precheck.policy_categories
    ))

    organization_id = require_stable_organization_id(knowledge_root)
    checksum = _content_checksum(content)
    if source_external_id:
        for evidence_path in sorted((knowledge_root / "evidence").rglob("*.md")):
            if evidence_path.name in {"index.md", "log.md"}:
                continue
            evidence = parse_markdown(evidence_path)
            source_ref = evidence.frontmatter.get("source_ref")
            if evidence.frontmatter.get("provider") == provider and isinstance(source_ref, dict) and source_ref.get("external_id") == source_external_id.strip() and evidence.frontmatter.get("checksum") == checksum:
                return CaptureResult(None, None, checksum, True, evidence_id=str(evidence.frontmatter.get("id")), evidence_path=evidence_path)
    ingested = _reuse_ingested_capture(
        knowledge_root, provider, idempotency_key.strip(), checksum
    )
    if ingested:
        return ingested
    inbox_root = knowledge_root.resolve() / "inbox" / provider
    inbox_root.mkdir(parents=True, exist_ok=True)
    for existing_path in sorted(inbox_root.glob("*.md")):
        try:
            existing, _ = read_conversation_intake(existing_path)
        except (OSError, ValueError):
            continue
        if existing.get("idempotency_key") != idempotency_key:
            continue
        if existing.get("checksum") != checksum:
            raise CaptureIdempotencyConflict(
                intake_id=str(existing["id"]), inbox_path=existing_path,
                existing_checksum=str(existing["checksum"]), supplied_checksum=checksum,
            )
        return CaptureResult(str(existing["id"]), existing_path, checksum, True)
    intake_uuid = str(uuid4())
    now = captured_at or datetime.now(timezone.utc)
    intake_id = f"inbox://{organization_id}/{provider}/{intake_uuid}"
    path = inbox_root / f"{_slug(title)}-{intake_uuid}.md"
    frontmatter = {
        "type": "inbox_item",
        "id": intake_id,
        "title": title.strip(),
        "provider": provider,
        "content_type": "document",
        "captured_at": now.isoformat(timespec="seconds"),
        "captured_from": captured_from,
        "source_url": source_url or "",
        "source_locator": source_locator or "",
        "status": "pending",
        "checksum": checksum,
        "idempotency_key": idempotency_key.strip(),
        "why_collected": why_collected.strip(),
        "intended_use": [item.strip() for item in intended_use],
        "sensitivity_review": "required",
    }
    details = dict(capture_details or {})
    if masked_categories or policy_categories:
        details["sensitive_data_precheck"] = {
            "masked": bool(masked_categories),
            "categories": masked_categories,
            "policy_categories": policy_categories,
        }
    if details:
        frontmatter["capture_details"] = details
    path.write_text(
        render_markdown(
            frontmatter,
            "# Inbox Document\n\n"
            f"{INBOX_CONTENT_START}{content}{INBOX_CONTENT_END}\n",
        ),
        encoding="utf-8",
    )
    ensure_inbox_task(knowledge_root, intake_id=intake_id, inbox_path=path)
    enqueue_inbox_review(
        knowledge_root, intake_id=intake_id, inbox_path=path,
        current_stage="sensitivity_review",
        reason_code="sensitivity_review_required",
    )
    return CaptureResult(intake_id, path, checksum)


@_synchronized_capture
def capture_file(
    knowledge_root: Path, payload: bytes, original_filename: str, provider: str, *,
    title: str, why_collected: str, intended_use: List[str], idempotency_key: str,
    source_url: Optional[str] = None, source_locator: Optional[str] = None,
    captured_from: str = "upload",
) -> CaptureResult:
    """Land a binary or arbitrary file with a self-contained Inbox envelope."""
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("file payload must be non-empty bytes")
    if not isinstance(original_filename, str) or Path(original_filename).name != original_filename:
        raise ValueError("original_filename must be a basename")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("provider must contain only lowercase letters, digits, underscores, or hyphens")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be non-empty")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
    if captured_from not in {"api", "webhook", "manual", "upload", "sync"}:
        raise ValueError("captured_from is invalid")
    organization_id = require_stable_organization_id(knowledge_root)
    checksum = "sha256:" + hashlib.sha256(payload).hexdigest()
    ingested = _reuse_ingested_capture(
        knowledge_root, provider, idempotency_key.strip(), checksum
    )
    if ingested:
        return ingested
    inbox_root = knowledge_root.resolve() / "inbox" / provider
    inbox_root.mkdir(parents=True, exist_ok=True)
    for existing_path in sorted(inbox_root.glob("*.md")):
        try:
            existing, _ = read_conversation_intake(existing_path)
        except (OSError, ValueError):
            continue
        if existing.get("idempotency_key") == idempotency_key:
            if existing.get("checksum") != checksum:
                raise CaptureIdempotencyConflict(
                    intake_id=str(existing["id"]), inbox_path=existing_path,
                    existing_checksum=str(existing["checksum"]), supplied_checksum=checksum,
                )
            return CaptureResult(str(existing["id"]), existing_path, checksum, True)
    intake_uuid = str(uuid4())
    suffix = Path(original_filename).suffix.lower()
    payload_name = f"{_slug(Path(original_filename).stem)}-{intake_uuid}{suffix}"
    payload_path = inbox_root / payload_name
    payload_path.write_bytes(payload)
    intake_id = f"inbox://{organization_id}/{provider}/{intake_uuid}"
    envelope = inbox_root / f"{_slug(Path(original_filename).stem)}-{intake_uuid}.inbox.md"
    frontmatter = {
        "type": "inbox_item", "id": intake_id, "title": title.strip(), "provider": provider,
        "content_type": "file", "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "captured_from": captured_from, "source_url": source_url or "", "source_locator": source_locator or "",
        "status": "pending", "checksum": checksum, "payload_file": payload_name,
        "idempotency_key": idempotency_key.strip(), "why_collected": why_collected.strip(),
        "intended_use": [item.strip() for item in intended_use], "sensitivity_review": "required",
    }
    envelope.write_text(render_markdown(frontmatter, "# Inbox File\n\nPending inspection.\n"), encoding="utf-8")
    ensure_inbox_task(knowledge_root, intake_id=intake_id, inbox_path=envelope)
    enqueue_inbox_review(
        knowledge_root, intake_id=intake_id, inbox_path=envelope,
        current_stage="sensitivity_review",
        reason_code="sensitivity_review_required",
    )
    return CaptureResult(intake_id, envelope, checksum)
