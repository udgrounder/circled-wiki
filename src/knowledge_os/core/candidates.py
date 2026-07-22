"""Reviewable Draft Bundle candidates derived from curated Evidence."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from knowledge_os.config.settings import load_settings

from .frontmatter import parse_markdown, render_markdown
from .repository import find_document_by_id, iter_documents
from .validator import validate_repository


REVIEW_STATES = {"pending", "needs_changes", "approved"}
REVIEW_ACTIONS = {"needs_changes", "approve", "reject", "merge"}


def list_curation_candidates(knowledge_root: Path) -> List[Dict[str, object]]:
    """List Draft Bundles awaiting, requiring, or having recorded review."""
    candidates: List[Dict[str, object]] = []
    for path in iter_documents(knowledge_root):
        if "bundles" not in path.parts or path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        data = document.frontmatter
        extensions = data.get("extensions", {})
        review_state = extensions.get("review_state") if isinstance(extensions, dict) else None
        if data.get("status") != "draft" or review_state not in REVIEW_STATES:
            continue
        curation = extensions.get("curation", {}) if isinstance(extensions, dict) else {}
        candidates.append({
            "id": data.get("id"),
            "title": data.get("title"),
            "type": data.get("type"),
            "summary": data.get("summary"),
            "review_state": review_state,
            "evidence": data.get("evidence", []),
            "generated_at": curation.get("generated_at") if isinstance(curation, dict) else None,
            "generation_reason": curation.get("generation_reason") if isinstance(curation, dict) else None,
            "recommendation": curation.get("recommendation") if isinstance(curation, dict) else None,
            "limitations": curation.get("limitations") if isinstance(curation, dict) else None,
            "existing_bundle_candidates": curation.get("existing_bundle_candidates", []) if isinstance(curation, dict) else [],
            "confidence": curation.get("confidence") if isinstance(curation, dict) else None,
            "path": path.relative_to(knowledge_root.parent).as_posix(),
        })
    return candidates


def curation_candidate_digest(knowledge_root: Path, *, waiting_days: int = 7) -> Dict[str, object]:
    """Summarize review backlog without altering candidate state."""
    if waiting_days < 1:
        raise ValueError("waiting_days must be positive")
    now = datetime.now(timezone.utc)
    candidates = list_curation_candidates(knowledge_root)
    by_state: Dict[str, int] = {state: 0 for state in REVIEW_STATES}
    long_waiting: List[Dict[str, object]] = []
    for candidate in candidates:
        state = str(candidate["review_state"])
        by_state[state] += 1
        generated_at = candidate.get("generated_at")
        if not isinstance(generated_at, str):
            continue
        try:
            age_days = (now - datetime.fromisoformat(generated_at.replace("Z", "+00:00"))).days
        except ValueError:
            continue
        if age_days >= waiting_days:
            long_waiting.append({"id": candidate["id"], "title": candidate["title"], "age_days": age_days, "review_state": state})
    return {"candidate_count": len(candidates), "by_review_state": by_state, "long_waiting": long_waiting, "waiting_days": waiting_days}


def curation_backlog_metrics(knowledge_root: Path) -> Dict[str, object]:
    """Return Evidence-to-candidate backlog metrics without persisting a dashboard."""
    now = datetime.now(timezone.utc)
    evidence_total = 0
    evidence_new = 0
    evidence_curated = 0
    new_age_days: List[int] = []
    for path in (knowledge_root / "evidence").rglob("*.md"):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        data = document.frontmatter
        if data.get("type") != "evidence":
            continue
        evidence_total += 1
        if data.get("curated_into"):
            evidence_curated += 1
        if data.get("status") == "new":
            evidence_new += 1
            captured_at = data.get("captured_at")
            if isinstance(captured_at, str):
                try:
                    new_age_days.append((now - datetime.fromisoformat(captured_at.replace("Z", "+00:00"))).days)
                except ValueError:
                    pass
    candidates = list_curation_candidates(knowledge_root)
    by_domain: Dict[str, int] = {}
    for candidate in candidates:
        path = str(candidate.get("path", ""))
        parts = path.split("/")
        domain = parts[2] if len(parts) > 2 and parts[0:2] == ["knowledge", "bundles"] else "unknown"
        by_domain[domain] = by_domain.get(domain, 0) + 1
    return {
        "evidence_total": evidence_total,
        "evidence_curated": evidence_curated,
        "evidence_to_bundle_rate": 0.0 if evidence_total == 0 else round(evidence_curated / evidence_total, 4),
        "evidence_new": evidence_new,
        "new_evidence_max_age_days": max(new_age_days, default=0),
        "candidate_digest": curation_candidate_digest(knowledge_root),
        "candidate_domains": by_domain,
        "candidate_daily_transitions": curation_daily_transitions(knowledge_root),
    }


def curation_daily_transitions(knowledge_root: Path) -> Dict[str, int]:
    """Derive today's candidate creation and review transitions from stored history."""
    today = datetime.now(timezone.utc).date()
    counts = {"created": 0, "approved": 0, "needs_changes": 0, "rejected": 0, "merged": 0}
    for path in iter_documents(knowledge_root):
        if "bundles" not in path.parts or path.name in {"index.md", "log.md"}:
            continue
        data = parse_markdown(path).frontmatter
        extensions = data.get("extensions", {})
        curation = extensions.get("curation", {}) if isinstance(extensions, dict) else {}
        if not isinstance(curation, dict):
            continue
        if _is_today(curation.get("generated_at"), today):
            counts["created"] += 1
        history = curation.get("review_history", [])
        if not isinstance(history, list):
            continue
        for item in history:
            if not isinstance(item, dict) or not _is_today(item.get("at"), today):
                continue
            action = item.get("action")
            if action == "approve":
                counts["approved"] += 1
            elif action in {"needs_changes", "reject", "merge"}:
                counts[f"{action}"] += 1
    return counts


def _is_today(value: object, today) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date() == today
    except ValueError:
        return False


def promote_curation_candidate(
    knowledge_root: Path, bundle_id: str, *, actor: str, security_receipt: str,
) -> Dict[str, object]:
    """Promote an approved candidate only through the configured Owner gate."""
    settings = load_settings(knowledge_root.resolve().parent)
    owner = settings.approval.knowledge_owner
    if not owner:
        raise ValueError("Active promotion is disabled until approval.knowledge_owner is configured")
    if actor != owner:
        raise ValueError("only the configured knowledge-owner may promote a candidate")
    if not isinstance(security_receipt, str) or not security_receipt.strip():
        raise ValueError("security_receipt is required for Active promotion")
    document = find_document_by_id(knowledge_root, bundle_id)
    if document is None or "bundles" not in document.path.parts:
        raise ValueError("bundle_id must refer to an existing Bundle")
    data = dict(document.frontmatter)
    extensions = dict(data.get("extensions", {}))
    if data.get("status") != "draft" or extensions.get("review_state") != "approved":
        raise ValueError("only an approved Draft candidate may be promoted")
    curation = dict(extensions.get("curation", {}))
    if not curation:
        raise ValueError("only a Curation candidate may be promoted")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    governance = {
        "reviewed_at": now, "review_due_at": now,
        "freshness_policy": "on_change",
    }
    if data.get("type") == "runbook":
        governance.update({
            "freshness_policy": "risk_based", "risk_tier": "medium",
            "source_volatility": "periodic", "validity_days": 1,
            "change_triggers": ["user_requested"],
        })
    curation["promotion"] = {
        "approved_by": actor, "approved_at": now,
        "security_receipt": security_receipt.strip(),
    }
    extensions["curation"] = curation
    extensions["governance"] = governance
    data["status"] = "active"
    data["owners"] = [actor]
    data["updated_at"] = now
    data["extensions"] = extensions
    original = document.path.read_text(encoding="utf-8")
    try:
        document.path.write_text(render_markdown(data, document.body), encoding="utf-8")
        invalid = [item for item in validate_repository(knowledge_root) if not item.is_valid]
        if invalid:
            errors = [error for item in invalid for error in item.okf_errors + item.profile_errors]
            raise ValueError("candidate promotion validation failed: " + "; ".join(errors))
    except Exception:
        document.path.write_text(original, encoding="utf-8")
        raise
    return {"bundle_id": bundle_id, "status": "active", "approved_by": actor, "security_receipt": security_receipt.strip()}


def review_curation_candidate(
    knowledge_root: Path,
    bundle_id: str,
    *,
    action: str,
    actor: str,
    note: str = "",
    merged_into: Optional[str] = None,
) -> Dict[str, object]:
    """Record a review decision without auto-promoting a Draft to active knowledge."""
    if action not in REVIEW_ACTIONS:
        raise ValueError("action must be needs_changes, approve, reject, or merge")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    document = find_document_by_id(knowledge_root, bundle_id)
    if document is None or "bundles" not in document.path.parts:
        raise ValueError("bundle_id must refer to an existing Bundle")
    data = dict(document.frontmatter)
    if data.get("status") != "draft":
        raise ValueError("only Draft Bundles can be reviewed as candidates")
    extensions = dict(data.get("extensions", {}))
    if extensions.get("review_state") not in REVIEW_STATES:
        raise ValueError("Bundle is not a reviewable curation candidate")
    curation = dict(extensions.get("curation", {}))
    generated_by = str(curation.get("generated_by", "")).strip()
    if generated_by and actor.strip() == generated_by:
        raise ValueError("curation candidate reviewer must differ from the generating actor")
    if action == "merge":
        if not isinstance(merged_into, str) or not merged_into.strip() or merged_into == bundle_id:
            raise ValueError("merge requires a different target Bundle ID")
        target = find_document_by_id(knowledge_root, merged_into)
        if target is None or "bundles" not in target.path.parts:
            raise ValueError("merged_into must refer to an existing Bundle")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    history = list(curation.get("review_history", []))
    history.append({"action": action, "actor": actor.strip(), "at": now, "note": note.strip()})
    curation["review_history"] = history
    curation["reviewed_by"] = actor.strip()
    curation["reviewed_at"] = now
    if action == "needs_changes":
        extensions["review_state"] = "needs_changes"
    elif action == "approve":
        # Active promotion is deliberately a separate security and Owner-gated operation.
        extensions["review_state"] = "approved"
    else:
        data["status"] = "archived"
        extensions["review_state"] = "rejected" if action == "reject" else "merged"
        if action == "merge":
            curation["merged_into"] = merged_into
        extensions["archive"] = {
            "archived_at": now,
            "archived_by": actor.strip(),
            "reason": note.strip() or ("merged into another Bundle" if action == "merge" else "curation candidate rejected"),
            "restore_condition": "A reviewer explicitly reopens this curation candidate.",
        }
    extensions["curation"] = curation
    data["extensions"] = extensions
    original = document.path.read_text(encoding="utf-8")
    try:
        document.path.write_text(render_markdown(data, document.body), encoding="utf-8")
        invalid = [result for result in validate_repository(knowledge_root) if not result.is_valid]
        if invalid:
            messages = [
                error for result in invalid
                for error in result.okf_errors + result.profile_errors
            ]
            raise ValueError("candidate review validation failed: " + "; ".join(messages))
    except Exception:
        document.path.write_text(original, encoding="utf-8")
        raise
    return {
        "bundle_id": bundle_id,
        "status": data["status"],
        "review_state": extensions["review_state"],
        "reviewed_by": actor.strip(),
        "reviewed_at": now,
        "merged_into": curation.get("merged_into"),
    }
