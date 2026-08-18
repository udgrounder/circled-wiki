"""Deterministic, non-writing curation proposals for Evidence review."""

import json
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from ..config.curation_taxonomy import load_curation_taxonomy
from .evidence import evidence_content_mode, evidence_original_bytes, evidence_original_path
from .frontmatter import parse_markdown
from .repository import bundle_references_by_evidence, find_document_by_id, iter_documents
from .search import search_knowledge


TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".json"}


SearchCache = Dict[Tuple[str, Tuple[Tuple[str, str], ...]], list]


def propose_update(
    knowledge_root: Path, evidence_id: str, *, search_cache: Optional[SearchCache] = None,
) -> Dict[str, object]:
    """Produce a reviewable proposal; it never creates or changes a Bundle."""
    evidence = find_document_by_id(knowledge_root, evidence_id)
    if evidence is None or evidence.frontmatter.get("type") != "evidence":
        raise ValueError("evidence_id must refer to an existing Evidence Record")
    original = evidence_original_path(evidence)
    original_bytes = evidence_original_bytes(evidence)
    excerpt = _read_excerpt(evidence, original_bytes)
    query = str(evidence.frontmatter.get("title", ""))
    extensions = evidence.frontmatter.get("extensions", {})
    capture_context = extensions.get("capture_context", {}) if isinstance(extensions, dict) else {}
    routing_hints, taxonomy_configured = _routing_hints(
        knowledge_root, str(evidence.frontmatter.get("title", "")), capture_context,
    )
    candidates = []
    for candidate_query in _candidate_queries(query, capture_context):
        candidates += _cached_search(knowledge_root, candidate_query, {}, search_cache)
        candidates += _cached_search(
            knowledge_root, candidate_query, {"status": "draft"}, search_cache
        )
    candidates = list({hit.document_id: hit for hit in candidates}.values())
    candidates = [
        hit for hit in candidates
        if hit.document_type != "evidence"
        and hit.document_id != evidence_id
        and _is_semantically_related(hit.title, hit.summary, query, capture_context)
    ]
    active_candidates = [candidate for candidate in candidates if candidate.status == "active"]
    draft_candidates = [candidate for candidate in candidates if candidate.status == "draft"]
    creation_authorized = not candidates and len(routing_hints) == 1 and bool(routing_hints[0].get("auto_create"))
    recommended_action = "request_new_bundle"
    if active_candidates:
        recommended_action = "review_existing_bundle"
    elif draft_candidates:
        recommended_action = (
            "assign_owner_and_review_draft"
            if any(not candidate.owners for candidate in draft_candidates)
            else "review_draft_bundle"
        )
    elif creation_authorized:
        recommended_action = "create_draft_bundle"
    return {
        "evidence_id": evidence_id,
        "source_uuid": evidence.frontmatter["source_uuid"],
        "original_available": original_bytes is not None,
        "excerpt": excerpt,
        "evidence_freshness": _evidence_freshness(evidence),
        "source_lineage": _source_lineage(knowledge_root, evidence),
        "reference_transition_plan": _reference_transition_plan(knowledge_root, evidence),
        "candidate_bundles": [
            _candidate_metadata(knowledge_root, hit)
            for hit in candidates
        ],
        "capture_context": capture_context,
        "routing_hints": routing_hints,
        "creation_authorized": creation_authorized,
        "proposal_interpretation": {
            "routing_hints": (
                "Installation-local taxonomy policy hints. They define an approved "
                "new-Bundle route only through creation_authorized; they do not select "
                "an existing Bundle or replace semantic, security, review, or publication Gates."
            ),
            "suggested_bundle_type": (
                "Non-binding heuristic inferred from the Evidence excerpt and capture context. "
                "It is not a taxonomy rule and does not authorize creation or reclassification."
            ),
            "candidate_bundles": (
                "Keyword and frontmatter discovery candidates, filtered by a lightweight "
                "semantic relevance check. An empty list is not proof that no relevant Bundle exists."
            ),
            "creation_authorized": (
                "The only proposal field that authorizes automatic new Draft consideration: "
                "there must be no discovered candidate and exactly one matching auto_create taxonomy rule. "
                "All remaining Gates still apply."
            ),
        },
        "taxonomy_status": {
            "configured": taxonomy_configured,
            "next_action": (
                "Use the installation-local taxonomy as approved classification policy; existing Bundle selection and all Gates still apply."
                if taxonomy_configured else
                "Inspect relevant existing Bundles and request user approval for a curation-taxonomy.yaml draft; do not create it automatically."
            ),
        },
        "suggested_bundle_type": _suggest_bundle_type(excerpt, capture_context),
        "promotion_candidates": _promotion_candidates(original, original_bytes),
        "recommended_action": recommended_action,
        "blocking_conditions": [
            "draft_bundle_owner_missing"
            for candidate in draft_candidates
            if not candidate.owners
        ],
        "constraints": [
            "A human or LLM Curator must verify semantic relevance before publication.",
            "Any resulting Bundle must pass both OKF and the configured organization Profile validation.",
        ],
    }


def _routing_hints(knowledge_root: Path, title: str, capture_context: object) -> tuple[List[Dict[str, object]], bool]:
    """Return matching installation-local hints without making a routing decision."""
    context = title
    if isinstance(capture_context, dict):
        intended_use = capture_context.get("intended_use", [])
        if isinstance(intended_use, list):
            context += " " + " ".join(map(str, intended_use))
    normalized = context.casefold()
    taxonomy = load_curation_taxonomy(knowledge_root.resolve().parent)
    return ([
        {
            "match_terms": list(rule.match_terms),
            **({"description": rule.description} if rule.description else {}),
            "domain": rule.domain,
            "bundle_type": rule.bundle_type,
            "auto_create": rule.auto_create,
            **({"slug_prefix": rule.slug_prefix} if rule.slug_prefix else {}),
        }
        for rule in taxonomy.routing_rules
        if all(term in normalized for term in rule.match_terms)
    ], taxonomy.configured)


def _cached_search(
    knowledge_root: Path, query: str, filters: Dict[str, str], cache: Optional[SearchCache],
) -> list:
    if cache is None:
        return search_knowledge(knowledge_root, query, filters)
    key = (query, tuple(sorted(filters.items())))
    if key not in cache:
        cache[key] = search_knowledge(knowledge_root, query, filters)
    return cache[key]


def _candidate_metadata(knowledge_root: Path, hit) -> Dict[str, object]:
    """Expose safe Bundle frontmatter needed for deterministic target selection."""
    document = find_document_by_id(knowledge_root, hit.document_id)
    data = document.frontmatter if document is not None else {}
    tags = data.get("tags", [])
    evidence_ids = data.get("evidence", [])
    return {
        "id": hit.document_id,
        "title": hit.title,
        "summary": hit.summary,
        "status": hit.status,
        "owners": hit.owners,
        "review_requested": hit.review_requested,
        "bundle_type": data.get("type"),
        "domain": _bundle_domain(knowledge_root, hit.path),
        "tags": [str(tag) for tag in tags] if isinstance(tags, list) else [],
        "evidence_ids": [str(item) for item in evidence_ids] if isinstance(evidence_ids, list) else [],
        "body_checksum": "sha256:" + hashlib.sha256(document.body.encode("utf-8")).hexdigest() if document is not None else None,
        "latest_evidence_at": _latest_evidence_at(knowledge_root, evidence_ids),
    }


def _bundle_domain(knowledge_root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(knowledge_root / "bundles")
    except ValueError:
        return ""
    return relative.parts[0] if relative.parts else ""


def _evidence_freshness(evidence) -> Dict[str, object]:
    data = evidence.frontmatter
    source_ref = data.get("source_ref")
    snapshot_at = source_ref.get("snapshot_at") if isinstance(source_ref, dict) else None
    captured_at = data.get("captured_at")
    effective_at = _normalized_timestamp(snapshot_at) or _normalized_timestamp(captured_at)
    return {
        "effective_at": effective_at,
        "captured_at": captured_at if isinstance(captured_at, str) else None,
        "source_snapshot_at": snapshot_at if isinstance(snapshot_at, str) else None,
        "provider": data.get("provider"),
        "source_external_id": source_ref.get("external_id") if isinstance(source_ref, dict) else None,
    }


def _source_lineage(knowledge_root: Path, evidence) -> Dict[str, object]:
    """Return immutable Evidence snapshots that share an external source identity."""
    data = evidence.frontmatter
    source_ref = data.get("source_ref")
    external_id = source_ref.get("external_id") if isinstance(source_ref, dict) else None
    provider = data.get("provider")
    if not isinstance(provider, str) or not isinstance(external_id, str) or not external_id.strip():
        return {"available": False, "reason": "source_external_id_missing", "evidence": []}
    snapshots = []
    for path in iter_documents(knowledge_root):
        if "evidence" not in path.parts or path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        candidate_ref = document.frontmatter.get("source_ref")
        if document.frontmatter.get("provider") != provider or not isinstance(candidate_ref, dict) or candidate_ref.get("external_id") != external_id:
            continue
        snapshots.append({
            "evidence_id": document.frontmatter.get("id"),
            "checksum": document.frontmatter.get("checksum"),
            "effective_at": _evidence_freshness(document).get("effective_at"),
        })
    snapshots.sort(key=lambda item: _timestamp_sort_key(item["effective_at"]) if isinstance(item.get("effective_at"), str) else datetime.min.replace(tzinfo=timezone.utc))
    current_id = data.get("id")
    previous = [item["evidence_id"] for item in snapshots if item.get("evidence_id") != current_id]
    return {"available": True, "provider": provider, "external_id": external_id, "evidence": snapshots, "previous_evidence_ids": previous}


def _reference_transition_plan(knowledge_root: Path, evidence) -> List[Dict[str, object]]:
    lineage = _source_lineage(knowledge_root, evidence)
    if not lineage.get("available"):
        return []
    references = bundle_references_by_evidence(knowledge_root)
    current_id = str(evidence.frontmatter.get("id"))
    return [
        {"bundle_id": bundle_id, "replace_evidence_id": previous_id, "with_evidence_id": current_id}
        for previous_id in lineage["previous_evidence_ids"]
        for bundle_id in sorted(references.get(str(previous_id), set()))
        if previous_id != current_id
    ]


def _latest_evidence_at(knowledge_root: Path, evidence_ids: object) -> Optional[str]:
    if not isinstance(evidence_ids, list):
        return None
    timestamps = []
    for evidence_id in evidence_ids:
        evidence = find_document_by_id(knowledge_root, str(evidence_id))
        if evidence is None or evidence.frontmatter.get("type") != "evidence":
            continue
        effective_at = _evidence_freshness(evidence).get("effective_at")
        if isinstance(effective_at, str):
            timestamps.append(effective_at)
    return max(timestamps, key=_timestamp_sort_key) if timestamps else None


def _normalized_timestamp(value: object) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _timestamp_sort_key(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_semantically_related(
    title: str, summary: str, evidence_title: str, capture_context: object
) -> bool:
    """Reject loose matches such as a shared document type or the word 'runbook'."""
    candidate_tokens = _meaningful_tokens(f"{title} {summary}")
    evidence_text = evidence_title
    if isinstance(capture_context, dict):
        intended_use = capture_context.get("intended_use", [])
        if isinstance(intended_use, list):
            evidence_text += " " + " ".join(map(str, intended_use))
    evidence_tokens = _meaningful_tokens(evidence_text)
    overlap = candidate_tokens & evidence_tokens
    return len(overlap) >= 2 or bool(candidate_tokens & {evidence_title.strip().lower()})


def _meaningful_tokens(value: str) -> set[str]:
    ignored = {"runbook", "guide", "rulebook", "test", "tests", "운영", "절차", "문서"}
    return {
        token.lower()
        for token in re.findall(r"[0-9A-Za-z가-힣]+", value)
        if len(token) >= 2 and token.lower() not in ignored
    }


def _suggest_bundle_type(excerpt: str, capture_context: object) -> str:
    """Provide a non-binding curation hint; the Curator still makes the decision."""
    intended_use = []
    if isinstance(capture_context, dict):
        value = capture_context.get("intended_use", [])
        intended_use = [str(item).lower() for item in value] if isinstance(value, list) else []
    content = (excerpt + " " + " ".join(intended_use)).lower()
    if any(token in content for token in ("현황", "상태 보고", "status report", "weekly report", "monthly report", "snapshot", "as of")):
        return "report"
    if any(token in content for token in ("manual", "매뉴얼", "사용법", "사용 방법", "관리자 안내")):
        return "manual"
    if any(token in content for token in ("runbook", "장애 대응", "복구", "롤백", "incident", "rollback", "checklist")):
        return "runbook"
    if any(token in content for token in ("정책", "필수", "금지", "policy", "must not", "required")):
        return "policy"
    if any(token in content for token in ("결정", "선택 근거", "대안", "decision", "trade-off")):
        return "decision"
    if any(token in content for token in ("명세", "스키마", "요구사항", "specification", "schema", "contract")):
        return "spec"
    if any(token in content for token in ("참조", "용어", "정의", "reference", "glossary", "lookup")):
        return "reference"
    return "guide"


def _candidate_queries(title: str, capture_context: object) -> List[str]:
    queries = [title.strip()] if title.strip() else []
    if isinstance(capture_context, dict):
        intended_use = capture_context.get("intended_use", [])
        if isinstance(intended_use, list):
            queries.extend(
                str(item).replace("-", " ").replace("_", " ").strip()
                for item in intended_use
                if str(item).strip()
            )
    queries.extend(
        token for token in re.findall(r"[0-9A-Za-z가-힣]+", title)
        if len(token) >= 2
    )
    return list(dict.fromkeys(query for query in queries if query))


def _promotion_candidates(path: Path, original_bytes: Optional[bytes] = None) -> List[Dict[str, str]]:
    """Recognize structured Outcome originals in either file or embedded form."""
    if original_bytes is None:
        if not path.is_file() or path.suffix.lower() != ".json":
            return []
        try:
            original_bytes = path.read_bytes()
        except OSError:
            return []
    try:
        payload = json.loads(original_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return []
    if payload.get("type") != "workflow-outcome":
        return []
    candidates = [
        {
            "target_type": "runbook",
            "reason": "Review repeatable step, validation, and failure-handling changes.",
        }
    ]
    if payload.get("learnings"):
        candidates.append(
            {
                "target_type": "guide",
                "reason": "Review generalizable learnings before organizational reuse.",
            }
        )
    if payload.get("artifacts"):
        candidates.append(
            {
                "target_type": "workflow-example",
                "reason": "Link approved artifact metadata as a Runbook outcome example.",
            }
        )
    return candidates


def _read_excerpt(document, content: bytes, limit: int = 2000) -> str:
    if content is None:
        return ""
    path = evidence_original_path(document)
    if evidence_content_mode(document) != "embedded" and path.suffix.lower() not in TEXT_EXTENSIONS:
        return "[Binary original: inspect via its preserved Evidence file.]"
    return content.decode("utf-8", errors="replace")[:limit]
