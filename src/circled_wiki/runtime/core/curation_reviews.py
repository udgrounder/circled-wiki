"""Git-tracked review cards between external curation and Bundle mutation."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from copy import deepcopy
from typing import Dict, List, Optional
from uuid import uuid4

from .curation_contract import CurationOutput, validate_curation_output
from .curation_queue import (
    _complete_curation_work_unlocked,
    _enqueue_curation_work_unlocked,
    curation_queue_transaction,
)
from .curation_safety import curation_body_safety_errors
from .frontmatter import parse_markdown, render_markdown
from .repository import _apply_bundle_revision, find_document_by_id
from .validator import validate_document
from .bundle_types import DIRECT_DRAFT_TYPES, PRE_CREATION_REVIEW_TYPES
from .notification_store import dismiss_notifications_for_resource, record_user_notification


REVIEW_STATUSES = {"pending", "approved", "no_bundle", "needs_changes", "needs_review", "stale", "applied", "archived"}
# The automated Curation path may mutate every non-operational Bundle type.
# Runbooks and manuals always remain on the owner- and review-gated path.
AUTOMATIC_UPDATE_TYPES = DIRECT_DRAFT_TYPES


def list_curation_reviews(knowledge_root: Path, *, include_resolved: bool = False) -> List[Dict[str, object]]:
    """List review cards without exposing Evidence originals."""
    root = knowledge_root / "curation-reviews"
    reviews: List[Dict[str, object]] = []
    if not root.is_dir():
        return reviews
    for path in sorted(root.rglob("*.md")):
        if path.name in {"README.md", "index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        data = document.frontmatter
        if data.get("type") != "curation_review":
            continue
        if not include_resolved and data.get("status") not in {"pending", "needs_changes", "needs_review", "approved"}:
            continue
        refs = data.get("evidence_refs", [])
        reviews.append({
            "review_id": data.get("review_id"), "status": data.get("status"),
            "title": data.get("title"), "recommendation": data.get("recommendation"),
            "target_bundle_id": data.get("target_bundle_id"),
            "expected_knowledge_revision": data.get("expected_knowledge_revision"),
            "evidence_refs": refs, "path": path.relative_to(knowledge_root.parent).as_posix(),
        })
    return reviews


def generate_curation_review(
    knowledge_root: Path, evidence_id: str, output: CurationOutput, *, generated_by: str,
    curation_receipt: str, receipt_metadata: Optional[Dict[str, object]] = None,
    user_review_request: Optional[str] = None,
) -> Dict[str, object]:
    """Persist a safe, checksum-bound Review card only on an allowed route."""
    if not generated_by.strip() or not curation_receipt.strip():
        raise ValueError("generated_by and curation_receipt must be non-empty")
    requested_review = (user_review_request or "").strip()
    requires_type_review = (
        output.action != "no_bundle" and output.bundle_type in PRE_CREATION_REVIEW_TYPES
    )
    if output.action != "no_bundle" and not requires_type_review and not requested_review:
        raise ValueError(
            "non-runbook/manual Curation Reviews require an explicit user_review_request"
        )
    evidence = find_document_by_id(knowledge_root, evidence_id)
    if evidence is None or evidence.frontmatter.get("type") != "evidence":
        raise ValueError("evidence_id must refer to an existing Evidence Record")
    if output.evidence_ids != (evidence_id,):
        raise ValueError("single-Evidence review requires exactly its Evidence ID")
    if output.action != "no_bundle" and curation_body_safety_errors(output.body):
        raise ValueError("curation output safety check failed")

    checksum = str(evidence.frontmatter.get("checksum", ""))
    evidence_path = evidence.path.relative_to(knowledge_root).as_posix()
    target_bundle_id, expected_revision = _target_bundle(knowledge_root, output)
    _require_update_body_basis(knowledge_root, output, target_bundle_id)
    recommendation = "no_bundle" if output.action == "no_bundle" else (
        "update_existing" if target_bundle_id else "create_draft_bundle"
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    review_id = "review-" + str(uuid4())
    month = now[:7]
    path = knowledge_root / "curation-reviews" / month / f"{review_id}.md"
    payload = _output_payload(output)
    metadata: Dict[str, object] = {
        "generated_by": generated_by.strip(),
        "curation_receipt": curation_receipt.strip(), "output": payload,
        "verification_attempt_id": "verification-" + str(uuid4()),
        "review_route": (
            "no_bundle_decision" if output.action == "no_bundle" else
            "required_type" if requires_type_review else "explicit_user_request"
        ),
    }
    if requested_review:
        metadata["user_review_request"] = requested_review
    if receipt_metadata is not None:
        metadata["receipt"] = receipt_metadata
    data: Dict[str, object] = {
        "type": "curation_review", "review_id": review_id, "status": "pending",
        "title": _safe_title(output, evidence.frontmatter.get("title")), "created_at": now,
        "recommendation": recommendation,
        "evidence_refs": [{"evidence_id": evidence_id, "path": evidence_path, "checksum": checksum}],
        "target_bundle_id": target_bundle_id,
        "expected_knowledge_revision": expected_revision,
        "extensions": {"curation_review": {
            **metadata,
            # The card must stay reviewable even after its Evidence leaves the
            # Curator's work queue.  Keep only safe metadata here; the Evidence
            # original remains in its canonical record.
            "evidence_snapshot": _evidence_snapshot(evidence, evidence_path, checksum),
        }},
    }
    with curation_queue_transaction(knowledge_root):
        existing = _find_reusable_review(
            knowledge_root, evidence_id=evidence_id, checksum=checksum,
        )
        if existing is not None:
            _complete_curation_work_unlocked(knowledge_root, evidence_id)
            review_result = existing
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.write_text(render_markdown(data, _review_body(output)), encoding="utf-8")
                validation = validate_document(path, knowledge_root)
                if not validation.is_valid:
                    raise ValueError("curation review validation failed: " + "; ".join(validation.profile_errors))
                _complete_curation_work_unlocked(knowledge_root, evidence_id)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            review_result = {
                "action": "created_review", "review_id": review_id,
                "path": path.relative_to(knowledge_root.parent).as_posix(),
                "recommendation": recommendation,
            }
    try:
        notification = record_user_notification(
            knowledge_root.parent / "workspace",
            event="review_requested",
            priority="action_required",
            title="Curation 검토가 필요합니다",
            summary="Bundle 생성 또는 갱신에 대한 사용자 검토가 필요합니다.",
            next_action="Curation Review를 검토하고 승인, 보완 요청 또는 보류를 선택하세요.",
            resource_ref=str(review_result["path"]),
            approval_required=True,
            dedupe_key=f"review_requested:{review_result['review_id']}",
            related_evidence_id=evidence_id,
            related_bundle_id=target_bundle_id or "",
        )
        review_result["user_notification"] = notification
    except (OSError, ValueError) as error:
        review_result["notification_delivery_error"] = str(error)
    return review_result


def decide_curation_review(knowledge_root: Path, review_id: str, *, action: str, actor: str, note: str = "") -> Dict[str, object]:
    """Apply a human decision and discard the consumed review work card."""
    if action not in {"approve", "no_bundle", "needs_changes", "needs_review"}:
        raise ValueError("action must be approve, no_bundle, needs_changes, or needs_review")
    if not actor.strip():
        raise ValueError("actor must be non-empty")
    path, document = _find_review(knowledge_root, review_id)
    data = dict(document.frontmatter)
    if data.get("status") not in {"pending", "needs_changes", "needs_review", "approved"}:
        raise ValueError("resolved or stale review cannot be decided")
    metadata = data.get("extensions", {}).get("curation_review", {})
    if not isinstance(metadata, dict):
        raise ValueError("review metadata is missing")
    evidence_ref = _single_evidence_ref(data)
    evidence = find_document_by_id(knowledge_root, evidence_ref["evidence_id"])
    if evidence is None or evidence.frontmatter.get("checksum") != evidence_ref["checksum"]:
        _stale_review(path, data, document.body, knowledge_root, evidence)
        raise ValueError("Evidence changed; review is stale")
    payload = metadata.get("output")
    if not isinstance(payload, dict):
        raise ValueError("review output is missing")
    output = validate_curation_output(payload, [evidence_ref["evidence_id"]])
    recommendation = data.get("recommendation")
    delete_review_after_decision = False
    if action == "approve" and recommendation == "update_existing":
        current = find_document_by_id(knowledge_root, str(data.get("target_bundle_id") or ""))
        expected = data.get("expected_knowledge_revision")
        current_revision = current.frontmatter.get("extensions", {}).get("knowledge_revision") if current else None
        if current is None or current_revision != expected:
            _stale_review(path, data, document.body, knowledge_root, evidence)
            raise ValueError("target Bundle changed; review is stale")
        # A revision body/frontmatter is intentionally not applied implicitly.
        data["status"] = "approved"
        result: Dict[str, object] = {"action": "approved_update", "target_bundle_id": data.get("target_bundle_id")}
    elif action == "approve":
        from .curation import materialize_curation_candidate
        result = materialize_curation_candidate(
            knowledge_root, evidence_ref["evidence_id"], output,
            generated_by=str(metadata["generated_by"]), curation_receipt=str(metadata["curation_receipt"]),
            receipt_metadata=metadata.get("receipt") if isinstance(metadata.get("receipt"), dict) else None,
            approved_review_id=review_id,
        )
        data["status"] = "applied"
        delete_review_after_decision = True
    elif action == "no_bundle":
        from .curation import materialize_curation_candidate
        no_bundle = output if output.action == "no_bundle" else CurationOutput(
            action="no_bundle", domain="", bundle_type="", title="", summary="", body="",
            evidence_ids=(evidence_ref["evidence_id"],),
            rationale=note or "Reviewer determined no Bundle is needed.",
            recheck_condition="Evidence checksum changes or reviewer reopens the decision.",
        )
        result = materialize_curation_candidate(
            knowledge_root, evidence_ref["evidence_id"], no_bundle,
            generated_by=str(metadata["generated_by"]), curation_receipt=str(metadata["curation_receipt"]),
        )
        data["status"] = "no_bundle"
        delete_review_after_decision = True
    else:
        data["status"] = "needs_changes" if action == "needs_changes" else "needs_review"
        result = {"action": data["status"]}
    data["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["decided_by"] = actor.strip()
    data["decision_note"] = note
    metadata["verification"] = {
        "verified_by": actor.strip(), "verified_at": data["decided_at"],
        "verification_attempt_id": metadata["verification_attempt_id"],
        "evidence_checksum": evidence_ref["checksum"], "result": action,
    }
    extensions = dict(data.get("extensions", {}))
    extensions["curation_review"] = metadata
    data["extensions"] = extensions
    if delete_review_after_decision and action == "approve":
        bundle = find_document_by_id(knowledge_root, str(result.get("bundle_id", "")))
        if bundle is None:
            raise ValueError("created Draft must remain available before review cleanup")
        original_bundle = bundle.path.read_text(encoding="utf-8")
        bundle_data = dict(bundle.frontmatter)
        bundle_extensions = dict(bundle_data.get("extensions", {}))
        curation = dict(bundle_extensions.get("curation", {}))
        decision = {
            "review_id": review_id,
            "decided_at": data["decided_at"],
            "decided_by": data["decided_by"],
            "verification_attempt_id": metadata["verification_attempt_id"],
            "evidence_checksum": evidence_ref["checksum"],
            "decision_note": note,
        }
        curation.setdefault("creation_review_id", review_id)
        curation.setdefault("review_decision", decision)
        history = list(curation.get("review_receipts", []))
        history.append({**decision, "kind": "creation", "applied_revision": bundle_data["extensions"]["knowledge_revision"]})
        curation["review_receipts"] = history
        bundle_extensions["curation"] = curation
        bundle_data["extensions"] = bundle_extensions
        try:
            bundle.path.write_text(render_markdown(bundle_data, bundle.body), encoding="utf-8")
            validation = validate_document(bundle.path, knowledge_root)
            if not validation.is_valid:
                raise ValueError(
                    "approved Draft validation failed: "
                    + "; ".join(validation.profile_errors)
                )
            _archive_review(path, data, document.body)
        except Exception:
            bundle.path.write_text(original_bundle, encoding="utf-8")
            raise
        _dismiss_review_notification(knowledge_root, path)
        return {
            "review_id": review_id,
            "status": data["status"],
            "review_deleted": True,
            "result": result,
        }
    if delete_review_after_decision:
        _archive_review(path, data, document.body)
        _dismiss_review_notification(knowledge_root, path)
        return {
            "review_id": review_id,
            "status": data["status"],
            "review_deleted": True,
            "result": result,
        }
    path.write_text(render_markdown(data, document.body), encoding="utf-8")
    return {"review_id": review_id, "status": data["status"], "result": result}


def apply_approved_curation_update(
    knowledge_root: Path, review_id: str, *, actor: str,
) -> Dict[str, object]:
    """Apply one checksum- and revision-bound approved update review.

    This is intentionally the only update path that consumes an
    ``update_existing`` review.  It preserves the Bundle status and immutable
    identifiers, then archives the Review card as the durable decision receipt.
    """
    if not actor.strip():
        raise ValueError("actor must be non-empty")
    path, document = _find_review(knowledge_root, review_id)
    data = dict(document.frontmatter)
    if data.get("status") != "approved" or data.get("recommendation") != "update_existing":
        raise ValueError("review must be an approved update_existing review")
    metadata = data.get("extensions", {}).get("curation_review", {})
    if not isinstance(metadata, dict):
        raise ValueError("review metadata is missing")
    verification = metadata.get("verification")
    if not isinstance(verification, dict) or verification.get("result") != "approve":
        raise ValueError("approved review is missing its verification record")
    evidence_ref = _single_evidence_ref(data)
    evidence = find_document_by_id(knowledge_root, evidence_ref["evidence_id"])
    if evidence is None or evidence.frontmatter.get("checksum") != evidence_ref["checksum"]:
        _stale_review(path, data, document.body, knowledge_root, evidence)
        raise ValueError("Evidence changed; review is stale")
    target_id = str(data.get("target_bundle_id") or "")
    target = find_document_by_id(knowledge_root, target_id)
    expected_revision = data.get("expected_knowledge_revision")
    actual_revision = target.frontmatter.get("extensions", {}).get("knowledge_revision") if target else None
    if target is None or actual_revision != expected_revision:
        _stale_review(path, data, document.body, knowledge_root, evidence)
        raise ValueError("target Bundle changed; review is stale")
    payload = metadata.get("output")
    if not isinstance(payload, dict):
        raise ValueError("review output is missing")
    output = validate_curation_output(payload, [evidence_ref["evidence_id"]])
    if output.action != target.frontmatter.get("type"):
        raise ValueError("review Bundle type does not match the target Bundle")
    _require_update_body_basis(knowledge_root, output, target_id)

    proposed = deepcopy(target.frontmatter)
    proposed["title"] = output.title
    proposed["summary"] = output.summary
    proposed["tags"] = list(output.tags)
    proposed["evidence"] = list(dict.fromkeys([
        *[str(item) for item in target.frontmatter.get("evidence", [])],
        evidence_ref["evidence_id"],
    ]))
    extensions = dict(proposed.get("extensions", {}))
    curation = dict(extensions.get("curation", {}))
    decision = {
        "review_id": review_id,
        "decided_at": data.get("decided_at"),
        "decided_by": data.get("decided_by"),
        "verification_attempt_id": verification.get("verification_attempt_id"),
        "evidence_checksum": evidence_ref["checksum"],
        "decision_note": data.get("decision_note", ""),
    }
    history = list(curation.get("review_receipts", []))
    if not history and isinstance(curation.get("review_decision"), dict):
        history.append({**curation["review_decision"], "kind": "creation"})
    history.append({**decision, "kind": "update", "applied_revision": expected_revision + 1})
    curation["review_receipts"] = history
    extensions["curation"] = curation
    proposed["extensions"] = extensions
    original_bundle = target.path.read_text(encoding="utf-8")
    updated = _apply_bundle_revision(
        knowledge_root, bundle_id=target_id, expected_revision=expected_revision,
        proposed_frontmatter=proposed, body=_updated_body(target.body, output), actor=actor,
        allow_active_curation_revision=True,
    )
    data["status"] = "applied"
    data["applied_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["applied_by"] = actor.strip()
    try:
        _archive_review(path, data, document.body)
    except Exception:
        target.path.write_text(original_bundle, encoding="utf-8")
        if path.exists():
            path.write_text(render_markdown(document.frontmatter, document.body), encoding="utf-8")
        raise
    _dismiss_review_notification(knowledge_root, path)
    return {
        "review_id": review_id, "status": "applied", "bundle_id": target_id,
        "knowledge_revision": updated.frontmatter["extensions"]["knowledge_revision"],
    }


def _dismiss_review_notification(knowledge_root: Path, path: Path) -> None:
    """Do not leave a user-facing review request open after its source resolves."""
    try:
        dismiss_notifications_for_resource(
            knowledge_root.parent / "workspace",
            resource_ref=path.relative_to(knowledge_root.parent).as_posix(),
            reason="Curation Review resolved",
        )
    except (OSError, ValueError):
        # The review receipt is canonical; notification delivery must not undo it.
        pass


def apply_automatic_curation_update(
    knowledge_root: Path, evidence_id: str, output: CurationOutput, *, actor: str,
    curation_receipt: str, security_receipt: str,
) -> Dict[str, object]:
    """Apply a receipt-bound update for an existing non-operational Bundle.

    This path never changes identity, classification, ownership, workflow, rule
    metadata, or approval metadata.  Runbooks and manuals remain on the
    review-card path.
    """
    if not actor.strip() or not curation_receipt.strip() or not security_receipt.strip():
        raise ValueError("actor, curation_receipt, and security_receipt must be non-empty")
    if output.action not in AUTOMATIC_UPDATE_TYPES:
        raise ValueError("automatic update is not allowed for runbook or manual Bundles")
    if output.update_mode != "append":
        raise ValueError("automatic update requires append update_mode")
    if output.evidence_ids != (evidence_id,):
        raise ValueError("automatic update requires exactly its Evidence")
    if curation_body_safety_errors(output.body):
        raise ValueError("curation output safety check failed")
    evidence = find_document_by_id(knowledge_root, evidence_id)
    if evidence is None or evidence.frontmatter.get("type") != "evidence":
        raise ValueError("evidence_id must refer to an existing Evidence Record")
    target_id, expected_revision = _target_bundle(knowledge_root, output)
    target = find_document_by_id(knowledge_root, str(target_id or ""))
    if target is None or not isinstance(expected_revision, int):
        raise ValueError("automatic update requires an existing revisioned Bundle")
    if target.frontmatter.get("type") != output.action:
        raise ValueError("automatic update Bundle type does not match the target Bundle")
    _require_update_body_basis(knowledge_root, output, str(target_id))
    if not validate_document(target.path, knowledge_root).is_valid:
        raise ValueError("target Bundle must pass Validator before automatic update")

    proposed = deepcopy(target.frontmatter)
    # Deliberately keep type, status, owners, workflow, rulebook,
    # approvals and all unrelated extensions from the validated existing Bundle.
    proposed["title"] = output.title
    proposed["summary"] = output.summary
    proposed["tags"] = list(output.tags)
    proposed["evidence"] = list(dict.fromkeys([
        *[str(item) for item in target.frontmatter.get("evidence", [])], evidence_id,
    ]))
    extensions = dict(proposed.get("extensions", {}))
    curation = dict(extensions.get("curation", {}))
    receipts = list(curation.get("automatic_update_receipts", []))
    receipts.append({
        "evidence_id": evidence_id,
        "evidence_checksum": str(evidence.frontmatter["checksum"]),
        "expected_knowledge_revision": expected_revision,
        "applied_revision": expected_revision + 1,
        "curation_receipt": curation_receipt.strip(),
        "security_receipt": security_receipt.strip(),
        "applied_by": actor.strip(),
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    curation["automatic_update_receipts"] = receipts
    evidence_checksums = {}
    for current_evidence_id in proposed["evidence"]:
        current_evidence = find_document_by_id(knowledge_root, current_evidence_id)
        if current_evidence is None or current_evidence.frontmatter.get("type") != "evidence":
            raise ValueError("automatic update Evidence is unavailable")
        evidence_checksums[current_evidence_id] = str(current_evidence.frontmatter["checksum"])
    curation["evidence_checksums"] = evidence_checksums
    if len(evidence_checksums) == 1:
        curation["evidence_checksum"] = next(iter(evidence_checksums.values()))
    extensions["curation"] = curation
    proposed["extensions"] = extensions
    updated = _apply_bundle_revision(
        knowledge_root, bundle_id=str(target_id), expected_revision=expected_revision,
        proposed_frontmatter=proposed, body=_updated_body(target.body, output), actor=actor,
        allow_active_curation_revision=True,
    )
    return {
        "action": "updated", "bundle_id": str(target_id),
        "knowledge_revision": updated.frontmatter["extensions"]["knowledge_revision"],
        "promotion_mode": "automatic_update",
    }


def _target_bundle(knowledge_root: Path, output: CurationOutput):
    for bundle_id in output.existing_bundle_candidates:
        bundle = find_document_by_id(knowledge_root, bundle_id)
        revision = bundle.frontmatter.get("extensions", {}).get("knowledge_revision") if bundle else None
        if bundle is not None and isinstance(revision, int):
            return bundle_id, revision
    return None, None


def _require_update_body_basis(
    knowledge_root: Path, output: CurationOutput, target_bundle_id: Optional[str],
) -> None:
    """Bind update content to the exact Bundle body the Curator inspected."""
    if not output.existing_bundle_candidates:
        return
    if not target_bundle_id:
        raise ValueError("update_existing requires an existing target Bundle")
    target = find_document_by_id(knowledge_root, target_bundle_id)
    if target is None:
        raise ValueError("update_existing target Bundle is unavailable")
    actual = _body_checksum(target.body)
    if output.base_body_checksum != actual:
        raise ValueError("update_existing base_body_checksum does not match the target Bundle")


def _updated_body(current_body: str, output: CurationOutput) -> str:
    if output.update_mode == "append":
        return current_body.rstrip() + "\n\n" + output.body.strip() + "\n"
    return output.body


def _body_checksum(body: str) -> str:
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _find_reusable_review(
    knowledge_root: Path, *, evidence_id: str, checksum: str,
) -> Optional[Dict[str, object]]:
    """Find the existing live card for this Queue work, without a duplicate key."""
    for review in list_curation_reviews(knowledge_root, include_resolved=True):
        if review.get("status") not in {"pending", "needs_changes", "needs_review", "approved"}:
            continue
        try:
            ref = _single_evidence_ref({"evidence_refs": review.get("evidence_refs")})
        except ValueError:
            continue
        if ref["evidence_id"] != evidence_id or ref["checksum"] != checksum:
            continue
        review_path = knowledge_root.parent / str(review["path"])
        validation = validate_document(review_path, knowledge_root)
        if not validation.is_valid:
            raise ValueError(
                "existing curation review validation failed: "
                + "; ".join(validation.profile_errors)
            )
        return {
            "action": "reused_review", "review_id": review["review_id"],
            "path": str(review["path"]), "recommendation": review["recommendation"],
        }
    return None


def _output_payload(output: CurationOutput) -> Dict[str, object]:
    payload: Dict[str, object] = {}
    for name in output.__dataclass_fields__:
        value = getattr(output, name)
        payload[name] = list(value) if isinstance(value, tuple) else value
    return payload


def _safe_title(output: CurationOutput, evidence_title: object) -> str:
    value = output.title or str(evidence_title or "Curation review")
    return re.sub(r"\s+", " ", value).strip()[:160] or "Curation review"


def _review_body(output: CurationOutput) -> str:
    body = "# Review summary\n\n" + (output.summary or output.rationale or "Review the referenced Evidence before applying a change.") + "\n"
    if output.bundle_type in {"manual", "runbook"} and output.slug:
        body += "\n## Proposed identifier\n\n`" + output.slug + "`\n"
    return body


def _evidence_snapshot(evidence, evidence_path: str, checksum: str) -> Dict[str, object]:
    """Copy safe, checksum-bound context for a reviewer, never Evidence content."""
    extensions = evidence.frontmatter.get("extensions", {})
    context = extensions.get("capture_context", {}) if isinstance(extensions, dict) else {}
    return {
        "evidence_id": str(evidence.frontmatter["id"]),
        "path": evidence_path,
        "checksum": checksum,
        "title": str(evidence.frontmatter.get("title", "")),
        "provider": str(evidence.frontmatter.get("provider", "")),
        "captured_at": str(evidence.frontmatter.get("captured_at", "")),
        "why_collected": str(context.get("why_collected", "")) if isinstance(context, dict) else "",
        "intended_use": list(context.get("intended_use", [])) if isinstance(context, dict) and isinstance(context.get("intended_use"), list) else [],
    }


def _single_evidence_ref(data: Dict[str, object]) -> Dict[str, str]:
    refs = data.get("evidence_refs")
    if not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], dict):
        raise ValueError("review must contain exactly one Evidence reference")
    ref = refs[0]
    if not all(isinstance(ref.get(field), str) and ref[field] for field in ("evidence_id", "path", "checksum")):
        raise ValueError("review Evidence reference is invalid")
    return {field: str(ref[field]) for field in ("evidence_id", "path", "checksum")}


def _find_review(knowledge_root: Path, review_id: str):
    for review in list_curation_reviews(knowledge_root, include_resolved=True):
        if review.get("review_id") == review_id:
            path = knowledge_root.parent / str(review["path"])
            return path, parse_markdown(path)
    raise ValueError("curation review was not found")


def _archive_review(path: Path, data: Dict[str, object], body: str) -> Path:
    """Hide a consumed card while keeping its decision as a Git-tracked receipt."""
    archive_path = path.parent.parent / ".archive" / path.parent.name / path.name
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(data, body), encoding="utf-8")
    path.replace(archive_path)
    return archive_path


def _stale_review(
    path: Path, data: Dict[str, object], body: str, knowledge_root: Path, evidence
) -> None:
    """Archive an obsolete decision and make its Evidence eligible for a fresh proposal."""
    previous_status = data.get("status")
    with curation_queue_transaction(knowledge_root):
        data["status"] = "stale"
        archive_path = _archive_review(path, data, body)
        try:
            if evidence is not None:
                _enqueue_curation_work_unlocked(
                    knowledge_root,
                    str(evidence.frontmatter["id"]),
                    evidence.path,
                )
        except Exception:
            archive_path.replace(path)
            data["status"] = previous_status
            path.write_text(render_markdown(data, body), encoding="utf-8")
            raise
    _dismiss_review_notification(knowledge_root, path)
