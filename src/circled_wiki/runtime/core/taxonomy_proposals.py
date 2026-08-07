"""Persist approval-gated taxonomy proposals and their read-only impact lists."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, Iterable, List
from uuid import uuid4

from circled_wiki.config.settings import SAFE_IDENTIFIER

from .notification_store import record_user_notification, require_acknowledged_user_notification


def record_taxonomy_change_proposal(
    knowledge_root: Path, *, evidence_id: str, domain: str, bundle_type: str,
    rationale: str, impacted_bundle_ids: Iterable[str] = (),
) -> Dict[str, object]:
    """Record a proposed future classification; never writes taxonomy or Bundles.

    The caller supplies the Agent's route recommendation.  This durable record
    makes the approval request and any existing-Bundle impact list reviewable;
    an empty impact list explicitly means the proposal is future-facing only.
    """
    if not evidence_id.strip() or not rationale.strip():
        raise ValueError("evidence_id and rationale must be non-empty")
    if not SAFE_IDENTIFIER.fullmatch(domain) or not SAFE_IDENTIFIER.fullmatch(bundle_type):
        raise ValueError("domain and bundle_type must be safe lowercase identifiers")
    impacts = sorted({bundle_id.strip() for bundle_id in impacted_bundle_ids if bundle_id.strip()})
    workspace = knowledge_root.parent / "workspace"
    proposal_root = workspace / "taxonomy-proposals"
    dedupe_key = f"taxonomy_route:{evidence_id}:{domain}:{bundle_type}"
    for path in sorted(proposal_root.glob("proposal-*.json")) if proposal_root.is_dir() else []:
        payload = _read_json(path)
        if payload.get("dedupe_key") == dedupe_key and payload.get("status") == "awaiting_user":
            return {**payload, "reused": True}
    proposal_id = f"proposal-{uuid4()}"
    payload: Dict[str, object] = {
        "schema_version": 1,
        "proposal_id": proposal_id,
        "status": "awaiting_user",
        "kind": "taxonomy_route",
        "evidence_id": evidence_id.strip(),
        "proposed_route": {"domain": domain, "bundle_type": bundle_type},
        "rationale": rationale.strip(),
        "impacted_bundle_ids": impacts,
        "dedupe_key": dedupe_key,
        "created_at": _now(),
    }
    path = proposal_root / f"{proposal_id}.json"
    _write_json(path, payload)
    resource_ref = path.relative_to(knowledge_root.parent).as_posix()
    notification = record_user_notification(
        workspace,
        event="taxonomy_change_proposed",
        priority="action_required",
        title="Curation taxonomy 변경 제안이 있습니다",
        summary=(
            f"새 분류 경로({domain}/{bundle_type})에 대한 승인 검토가 필요합니다. "
            f"기존 Bundle 영향 후보는 {len(impacts)}건입니다."
        ),
        next_action="taxonomy 제안과 영향 목록을 검토한 뒤 승인하거나 보완을 요청하세요.",
        resource_ref=resource_ref,
        approval_required=True,
        dedupe_key=f"taxonomy_change_proposed:{dedupe_key}",
        related_evidence_id=evidence_id,
    )
    payload["user_notification"] = notification
    _write_json(path, payload)
    if impacts:
        payload["reclassification_notification"] = record_user_notification(
            workspace,
            event="reclassification_ready",
            priority="attention",
            title="기존 Bundle 재분류 영향 목록이 준비되었습니다",
            summary=f"taxonomy 변경 제안에 따라 검토할 기존 Bundle이 {len(impacts)}건 있습니다.",
            next_action="알림을 확인한 뒤, 필요한 Bundle에 대해서만 재분류를 명시적으로 요청하세요.",
            resource_ref=resource_ref,
            approval_required=True,
            dedupe_key=f"reclassification_ready:{dedupe_key}",
            related_evidence_id=evidence_id,
        )
        _write_json(path, payload)
    return {**payload, "path": resource_ref, "reused": False}


def require_reclassification_approval(
    knowledge_root: Path, *, notification_id: str, bundle_id: str, domain: str, bundle_type: str,
) -> Dict[str, object]:
    """Verify an acknowledged, impact-scoped reclassification request."""
    workspace = knowledge_root.parent / "workspace"
    notification = require_acknowledged_user_notification(
        workspace, notification_id=notification_id, event="reclassification_ready",
    )
    resource_ref = notification.get("resource_ref")
    if not isinstance(resource_ref, str) or not resource_ref.startswith("workspace/taxonomy-proposals/"):
        raise ValueError("reclassification notification must reference a taxonomy proposal")
    proposal_path = (knowledge_root.parent / resource_ref).resolve()
    proposal_root = (workspace / "taxonomy-proposals").resolve()
    if proposal_root not in proposal_path.parents:
        raise ValueError("taxonomy proposal path is invalid")
    proposal = _read_json(proposal_path)
    route = proposal.get("proposed_route")
    impacts = proposal.get("impacted_bundle_ids")
    if not isinstance(route, dict) or not isinstance(impacts, list):
        raise ValueError("taxonomy proposal is incomplete")
    if route.get("domain") != domain or route.get("bundle_type") != bundle_type:
        raise ValueError("reclassification target must match the acknowledged taxonomy proposal")
    if bundle_id not in impacts:
        raise ValueError("bundle_id is not in the acknowledged reclassification impact list")
    return proposal


def _read_json(path: Path) -> Dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"taxonomy proposal is invalid: {path.name}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"taxonomy proposal is invalid: {path.name}")
    return payload


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
