"""Git-tracked review cards between external curation and Bundle mutation."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Dict, List, Optional

from .curation_contract import CurationOutput, validate_curation_output
from .curation_safety import curation_body_safety_errors
from .frontmatter import parse_markdown, render_markdown
from .repository import find_document_by_id
from .validator import validate_document


REVIEW_STATUSES = {"pending", "approved", "no_bundle", "needs_changes", "needs_review", "stale", "applied", "archived"}


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
) -> Dict[str, object]:
    """Persist a safe, checksum-bound review card; never writes a Bundle."""
    if not generated_by.strip() or not curation_receipt.strip():
        raise ValueError("generated_by and curation_receipt must be non-empty")
    evidence = find_document_by_id(knowledge_root, evidence_id)
    if evidence is None or evidence.frontmatter.get("type") != "evidence":
        raise ValueError("evidence_id must refer to an existing Evidence Record")
    if output.evidence_ids != (evidence_id,):
        raise ValueError("single-Evidence review requires exactly its Evidence ID")
    if output.action != "no_bundle" and curation_body_safety_errors(output.body):
        raise ValueError("curation output safety check failed")

    checksum = str(evidence.frontmatter.get("checksum", ""))
    evidence_path = evidence.path.relative_to(knowledge_root.parent).as_posix()
    target_bundle_id, expected_revision = _target_bundle(knowledge_root, output)
    recommendation = "no_bundle" if output.action == "no_bundle" else (
        "update_existing" if target_bundle_id else "create_draft_bundle"
    )
    key_input = "|".join((evidence_id, checksum, recommendation, target_bundle_id or "", str(expected_revision or "")))
    idempotency_key = hashlib.sha256(key_input.encode("utf-8")).hexdigest()
    for review in list_curation_reviews(knowledge_root, include_resolved=True):
        review_path = knowledge_root.parent / str(review["path"])
        document = parse_markdown(review_path)
        metadata = document.frontmatter.get("extensions", {}).get("curation_review", {})
        if isinstance(metadata, dict) and metadata.get("idempotency_key") == idempotency_key and document.frontmatter.get("status") != "stale":
            return {"action": "reused_review", "review_id": document.frontmatter["review_id"], "path": str(review["path"])}

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    review_id = "review-" + idempotency_key[:16]
    month = now[:7]
    path = knowledge_root / "curation-reviews" / month / f"{review_id}.md"
    payload = _output_payload(output)
    metadata: Dict[str, object] = {
        "idempotency_key": idempotency_key, "generated_by": generated_by.strip(),
        "curation_receipt": curation_receipt.strip(), "output": payload,
    }
    if receipt_metadata is not None:
        metadata["receipt"] = receipt_metadata
    data: Dict[str, object] = {
        "type": "curation_review", "review_id": review_id, "status": "pending",
        "title": _safe_title(output, evidence.frontmatter.get("title")), "created_at": now,
        "recommendation": recommendation,
        "evidence_refs": [{"evidence_id": evidence_id, "path": evidence_path, "checksum": checksum}],
        "target_bundle_id": target_bundle_id,
        "expected_knowledge_revision": expected_revision,
        "extensions": {"curation_review": metadata},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    original_evidence = evidence.path.read_text(encoding="utf-8")
    try:
        path.write_text(render_markdown(data, _review_body(output)), encoding="utf-8")
        validation = validate_document(path, knowledge_root)
        if not validation.is_valid:
            raise ValueError("curation review validation failed: " + "; ".join(validation.profile_errors))
        evidence_data = dict(evidence.frontmatter)
        extensions = dict(evidence_data.get("extensions", {}))
        extensions["curation_review"] = {
            "review_id": review_id, "status": "pending", "evidence_checksum": checksum,
        }
        evidence_data["extensions"] = extensions
        evidence.path.write_text(render_markdown(evidence_data, evidence.body), encoding="utf-8")
    except Exception:
        path.unlink(missing_ok=True)
        evidence.path.write_text(original_evidence, encoding="utf-8")
        raise
    return {"action": "created_review", "review_id": review_id, "path": path.relative_to(knowledge_root.parent).as_posix(), "recommendation": recommendation}


def decide_curation_review(knowledge_root: Path, review_id: str, *, action: str, actor: str, note: str = "") -> Dict[str, object]:
    """Record a human decision and remove a consumed review after Draft creation."""
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
    if actor.strip() == metadata.get("generated_by") and action in {"approve", "no_bundle"}:
        raise ValueError("curation review decision actor must differ from the generating actor")
    evidence_ref = _single_evidence_ref(data)
    evidence = find_document_by_id(knowledge_root, evidence_ref["evidence_id"])
    if evidence is None or evidence.frontmatter.get("checksum") != evidence_ref["checksum"]:
        data["status"] = "stale"
        path.write_text(render_markdown(data, document.body), encoding="utf-8")
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
            data["status"] = "stale"
            path.write_text(render_markdown(data, document.body), encoding="utf-8")
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
        )
        data["status"] = "applied"
        delete_review_after_decision = True
    elif action == "no_bundle":
        from .curation import materialize_curation_candidate
        no_bundle = output if output.action == "no_bundle" else CurationOutput(
            action="no_bundle", rationale=note or "Reviewer determined no Bundle is needed.", recheck_condition="Evidence checksum changes or reviewer reopens the decision."
        )
        result = materialize_curation_candidate(
            knowledge_root, evidence_ref["evidence_id"], no_bundle,
            generated_by=str(metadata["generated_by"]), curation_receipt=str(metadata["curation_receipt"]),
        )
        data["status"] = "no_bundle"
    else:
        data["status"] = "needs_changes" if action == "needs_changes" else "needs_review"
        result = {"action": data["status"]}
    data["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["decided_by"] = actor.strip()
    data["decision_note"] = note
    if delete_review_after_decision:
        current_evidence = find_document_by_id(knowledge_root, evidence_ref["evidence_id"])
        bundle = find_document_by_id(knowledge_root, str(result.get("bundle_id", "")))
        if current_evidence is None or bundle is None:
            raise ValueError("created Draft and Evidence must remain available before review cleanup")
        original_evidence = current_evidence.path.read_text(encoding="utf-8")
        original_bundle = bundle.path.read_text(encoding="utf-8")
        evidence_data = dict(current_evidence.frontmatter)
        evidence_extensions = dict(evidence_data.get("extensions", {}))
        evidence_extensions.pop("curation_review", None)
        evidence_data["extensions"] = evidence_extensions
        bundle_data = dict(bundle.frontmatter)
        bundle_extensions = dict(bundle_data.get("extensions", {}))
        curation = dict(bundle_extensions.get("curation", {}))
        curation["review_decision"] = {
            "review_id": review_id,
            "decided_at": data["decided_at"],
            "decided_by": data["decided_by"],
            "decision_note": note,
        }
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
            current_evidence.path.write_text(
                render_markdown(evidence_data, current_evidence.body), encoding="utf-8"
            )
            path.unlink()
        except Exception:
            bundle.path.write_text(original_bundle, encoding="utf-8")
            current_evidence.path.write_text(original_evidence, encoding="utf-8")
            raise
        return {
            "review_id": review_id,
            "status": data["status"],
            "review_deleted": True,
            "result": result,
        }
    path.write_text(render_markdown(data, document.body), encoding="utf-8")
    evidence_data = dict(evidence.frontmatter)
    extensions = dict(evidence_data.get("extensions", {}))
    review_state = dict(extensions.get("curation_review", {}))
    review_state["status"] = data["status"]
    review_state["decided_at"] = data["decided_at"]
    extensions["curation_review"] = review_state
    evidence_data["extensions"] = extensions
    evidence.path.write_text(render_markdown(evidence_data, evidence.body), encoding="utf-8")
    return {"review_id": review_id, "status": data["status"], "result": result}


def _target_bundle(knowledge_root: Path, output: CurationOutput):
    for bundle_id in output.existing_bundle_candidates:
        bundle = find_document_by_id(knowledge_root, bundle_id)
        revision = bundle.frontmatter.get("extensions", {}).get("knowledge_revision") if bundle else None
        if bundle is not None and isinstance(revision, int):
            return bundle_id, revision
    return None, None


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
    return "# Review summary\n\n" + (output.summary or output.rationale or "Review the referenced Evidence before applying a change.") + "\n"


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
