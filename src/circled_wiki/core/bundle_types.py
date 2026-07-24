"""Canonical Bundle taxonomy and creation-gate policy."""

from typing import Dict, List


BUNDLE_TYPES = frozenset(
    {"policy", "guide", "runbook", "manual", "decision", "spec", "reference", "report"}
)
PRE_CREATION_REVIEW_TYPES = frozenset({"runbook", "manual"})
DIRECT_DRAFT_TYPES = BUNDLE_TYPES - PRE_CREATION_REVIEW_TYPES

_TYPE_DESCRIPTIONS = {
    "policy": "Normative rules, constraints, and required behavior.",
    "guide": "Explanatory guidance and recommended practices without step-by-step operating control.",
    "runbook": "Repeatable operational execution or incident procedure with validation and recovery steps.",
    "manual": "Step-by-step instructions for using or administering a product, system, or capability.",
    "decision": "A decision record with rationale, alternatives, and consequences.",
    "spec": "A precise requirement, contract, schema, or technical design.",
    "reference": "Stable facts, definitions, lookup material, and source-oriented background.",
    "report": "A time-bounded status, assessment, snapshot, or periodic report.",
}


def curation_taxonomy() -> List[Dict[str, object]]:
    """Return the complete machine-readable taxonomy for external Curators."""
    return [
        {
            "type": bundle_type,
            "description": _TYPE_DESCRIPTIONS[bundle_type],
            "requires_pre_creation_review": bundle_type in PRE_CREATION_REVIEW_TYPES,
        }
        for bundle_type in sorted(BUNDLE_TYPES)
    ]
