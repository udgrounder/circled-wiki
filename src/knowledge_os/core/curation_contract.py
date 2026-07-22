"""Typed boundary for untrusted LLM curation responses.

The adapter must validate a JSON object here before any Draft Bundle write is
attempted.  This keeps model prose, invented IDs, and partial responses out of
the repository write path.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Tuple


_ACTIONS = {"no_bundle", "policy", "guide", "runbook"}
_BUNDLE_TYPES = {"policy", "guide", "runbook"}
_SAFE_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class CurationOutput:
    action: str
    domain: str
    bundle_type: str
    title: str
    summary: str
    body: str
    evidence_ids: Tuple[str, ...]
    rationale: str = ""
    limitations: str = ""
    existing_bundle_candidates: Tuple[str, ...] = ()
    confidence: str = ""
    recheck_condition: str = ""


def validate_curation_output(
    payload: object, allowed_evidence_ids: Iterable[str]
) -> CurationOutput:
    """Validate an adapter response and prohibit evidence reference invention."""
    if not isinstance(payload, dict):
        raise ValueError("curation output must be a JSON object")
    allowed = tuple(allowed_evidence_ids)
    if not allowed or any(not isinstance(item, str) or not item for item in allowed):
        raise ValueError("allowed Evidence IDs must be a non-empty string collection")
    action = payload.get("action")
    if action not in _ACTIONS:
        raise ValueError("curation action must be no_bundle, policy, guide, or runbook")
    if action == "no_bundle":
        rationale = _required_string(payload, "rationale")
        recheck_condition = _required_string(payload, "recheck_condition")
        return CurationOutput(
            action=action, domain="", bundle_type="", title="", summary="", body="",
            evidence_ids=allowed, rationale=rationale, recheck_condition=recheck_condition,
        )
    domain = _required_string(payload, "domain")
    if not _SAFE_DOMAIN.fullmatch(domain):
        raise ValueError("curation domain must be a safe lowercase identifier")
    bundle_type = _required_string(payload, "bundle_type")
    if bundle_type not in _BUNDLE_TYPES or bundle_type != action:
        raise ValueError("curation bundle_type must match action")
    evidence_ids = _string_list(payload.get("evidence_ids"), "evidence_ids")
    if set(evidence_ids) != set(allowed) or len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("curation evidence_ids must exactly match the allowed Evidence IDs")
    existing = _string_list(payload.get("existing_bundle_candidates", []), "existing_bundle_candidates")
    return CurationOutput(
        action=action,
        domain=domain,
        bundle_type=bundle_type,
        title=_required_string(payload, "title"),
        summary=_required_string(payload, "summary"),
        body=_required_string(payload, "body"),
        evidence_ids=tuple(evidence_ids),
        rationale=_optional_string(payload, "rationale"),
        limitations=_optional_string(payload, "limitations"),
        existing_bundle_candidates=tuple(existing),
        confidence=_optional_string(payload, "confidence"),
    )


def _required_string(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"curation {field} must be a non-empty string")
    return value.strip()


def _optional_string(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field, "")
    if not isinstance(value, str):
        raise ValueError(f"curation {field} must be a string")
    return value.strip()


def _string_list(value: object, field: str) -> List[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"curation {field} must be a string array")
    return [item.strip() for item in value]
