"""Deterministic, non-writing curation proposals for Evidence review."""

import json
from pathlib import Path
import re
from typing import Dict, List, Optional

from .evidence import evidence_content_mode, evidence_original_bytes, evidence_original_path
from .repository import find_document_by_id
from .search import search_knowledge


TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".json"}


def propose_update(knowledge_root: Path, evidence_id: str) -> Dict[str, object]:
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
    candidates = []
    for candidate_query in _candidate_queries(query, capture_context):
        candidates += search_knowledge(knowledge_root, candidate_query)
        candidates += search_knowledge(
            knowledge_root, candidate_query, {"status": "draft"}
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
    recommended_action = "create_draft_bundle"
    if active_candidates:
        recommended_action = "review_existing_bundle"
    elif draft_candidates:
        recommended_action = (
            "assign_owner_and_review_draft"
            if any(not candidate.owners for candidate in draft_candidates)
            else "review_draft_bundle"
        )
    return {
        "evidence_id": evidence_id,
        "source_uuid": evidence.frontmatter["source_uuid"],
        "evidence_status": evidence.frontmatter["status"],
        "original_available": original_bytes is not None,
        "excerpt": excerpt,
        "candidate_bundles": [
            {
                "id": hit.document_id,
                "title": hit.title,
                "summary": hit.summary,
                "status": hit.status,
                "owners": hit.owners,
                "review_requested": hit.review_requested,
            }
            for hit in candidates
        ],
        "capture_context": capture_context,
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
    if any(token in content for token in ("runbook", "반복", "단계", "절차", "checklist")):
        return "runbook"
    if any(token in content for token in ("결정", "승인", "decision")):
        return "decision"
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
