"""Validated execution contracts for safe Inbox stage reconciliation."""

from pathlib import Path
from typing import Dict

import yaml


CONTRACT_INDEX_PATH = "contracts/index.yaml"
CONTRACT_NAME = "inbox_reconciliation"
CURATION_CONTRACT_NAME = "curation_reconciliation"
CONTRACT_VERSION = 1
CURATION_CONTRACT_VERSION = 1
REGISTRY_API_VERSION = "circled-wiki.contract-registry/v1"
REGISTRY_KIND = "reconciliation_contract_registry"
CONTRACT_API_VERSION = "circled-wiki.reconciliation-contract/v1"
CONTRACT_KIND = "reconciliation_contract"
REQUIRED_STAGES = {"pending", "accepted"}
SUPPORTED_TRANSITIONS = {
    "pending": {
        "profile": "inbox-inspection",
        "action": "accept_ready_inbox",
        "next_stage": "accepted",
        "on_blocked": {
            "task_contract": "inbox_reconciliation",
            "reasons": {
                "sensitivity_review_required": {
                    "current_stage": "sensitivity_review",
                    "requested_action": "complete_sensitivity_review",
                    "resolved_next_action": "reprocess_inbox",
                },
            },
        },
        "requires": {
            "required_metadata", "provider_folder", "content_checksum", "sensitivity_review_resolved",
        },
    },
    "accepted": {
        "profile": "evidence-ingest",
        "action": "scan_pii_then_ingest",
        "next_stage": "evidence",
        "on_blocked": {
            "task_contract": "inbox_reconciliation",
            "reasons": {
                "pii_scan_required": {
                    "current_stage": "pii_scan",
                    "requested_action": "record_inbox_pii_scan",
                    "resolved_next_action": "reprocess_inbox",
                },
                "pii_needs_review": {
                    "current_stage": "pii_scan",
                    "requested_action": "decide_safe_handling",
                    "resolved_next_action": "reprocess_inbox",
                },
            },
        },
        "requires": {"accepted_inspection", "pii_review_not_blocking"},
    },
}
SUPPORTED_INBOX_REVIEW_REQUIREMENTS = {
    reason: definition
    for transition in SUPPORTED_TRANSITIONS.values()
    for reason, definition in transition["on_blocked"]["reasons"].items()
}
SUPPORTED_CURATION_STAGES = {
    "queued": {
        "profile": "knowledge-curation",
        "action": "run_configured_curation_batch",
        "requires": {"curation_queue_item", "evidence_original_available", "evidence_security_gate"},
    },
}
SUPPORTED_CURATION_OUTCOMES = {
    "no_bundle": {
        "next_stage": "no_bundle_recorded",
        "queue_disposition": "complete",
        "terminal": True,
    },
    "review_handoff": {
        "next_stage": "review_handoff",
        "queue_disposition": "complete",
        "terminal": True,
    },
    "published": {
        "next_stage": "published",
        "queue_disposition": "complete",
        "terminal": True,
    },
    "draft_created": {
        "next_stage": "draft_created",
        "queue_disposition": "complete",
        "terminal": True,
    },
    "retryable_block": {
        "next_stage": "queued",
        "queue_disposition": "retain",
        "terminal": False,
        "reason_categories": {
            "configuration": {
                "reason_codes": ["adapter_disabled", "adapter_command_empty"],
                "safe_next_action": "configure_curation_adapter",
            },
            "evidence_source": {
                "reason_codes": ["evidence_original_unavailable"],
                "safe_next_action": "restore_evidence_original",
            },
            "gate": {
                "reason_codes": ["proposal_blocked", "contract_or_gate_rejected"],
                "safe_next_action": "resolve_curation_gate",
            },
            "adapter_execution": {
                "reason_codes": ["adapter_failed", "adapter_unavailable", "invalid_json", "timeout"],
                "safe_next_action": "retry_curation",
            },
        },
    },
}


def curation_blocker_policy(reason_code: str) -> Dict[str, str]:
    """Return the contract-defined operational category and safe action."""
    retryable = SUPPORTED_CURATION_OUTCOMES["retryable_block"]
    categories = retryable["reason_categories"]
    for category, policy in categories.items():
        if reason_code in policy["reason_codes"]:
            return {
                "category": category,
                "safe_next_action": policy["safe_next_action"],
            }
    raise ValueError("curation blocker reason_code is unsupported")


def inbox_contract_path(knowledge_root: Path) -> Path:
    """Resolve the installed contract registry, with a source-tree fallback."""
    project_root = knowledge_root.resolve().parent
    installed = project_root / ".circled-wiki" / "agent-rules" / CONTRACT_INDEX_PATH
    if installed.is_file():
        return installed
    source_tree = project_root / "agent-rules" / CONTRACT_INDEX_PATH
    if source_tree.is_file():
        return source_tree
    raise ValueError("Inbox contract registry is missing")


def load_inbox_contract(knowledge_root: Path) -> Dict[str, object]:
    """Load only the contract shape required by the Inbox reconciler."""
    loaded = _load_registered_contract(
        knowledge_root, CONTRACT_NAME, CONTRACT_VERSION, SUPPORTED_TRANSITIONS
    )
    return loaded


def load_curation_contract(knowledge_root: Path) -> Dict[str, object]:
    """Load the outcome-aware Curation reconciliation contract."""
    index_path, path, contract = _read_registered_contract(
        knowledge_root, CURATION_CONTRACT_NAME, CURATION_CONTRACT_VERSION
    )
    stages = contract.get("stages")
    if not isinstance(stages, dict) or set(stages) != set(SUPPORTED_CURATION_STAGES):
        raise ValueError("curation_reconciliation contract has required stages missing")
    queued = stages["queued"]
    expected = SUPPORTED_CURATION_STAGES["queued"]
    if not isinstance(queued, dict) or any(
        queued.get(field) != expected[field] for field in ("profile", "action")
    ) or set(queued.get("requires", [])) != expected["requires"]:
        raise ValueError("curation_reconciliation contract transition is unsupported: queued")
    outcomes = queued.get("outcomes")
    if not isinstance(outcomes, dict) or set(outcomes) != set(SUPPORTED_CURATION_OUTCOMES):
        raise ValueError("curation_reconciliation contract outcomes are incomplete")
    for name, expected_outcome in SUPPORTED_CURATION_OUTCOMES.items():
        if outcomes.get(name) != expected_outcome:
            raise ValueError(f"curation_reconciliation contract outcome is unsupported: {name}")
    return {"path": path, "version": CURATION_CONTRACT_VERSION, "contract": contract}


def _load_registered_contract(
    knowledge_root: Path, contract_name: str, expected_version: int,
    supported_transitions: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    """Load one registered contract and reject transitions the runtime does not support."""
    _index_path, path, contract = _read_registered_contract(
        knowledge_root, contract_name, expected_version
    )
    stages = contract.get("stages")
    required_stages = set(supported_transitions)
    if not isinstance(stages, dict) or not required_stages.issubset(stages):
        raise ValueError(f"{contract_name} contract has required stages missing")
    for stage in required_stages:
        definition = stages.get(stage)
        if not isinstance(definition, dict) or not all(
            isinstance(definition.get(field), str) and definition[field]
            for field in ("profile", "action", "next_stage")
        ) or not isinstance(definition.get("requires"), list):
            raise ValueError(f"{contract_name} contract stage is invalid: {stage}")
        expected = supported_transitions[stage]
        if any(definition[field] != expected[field] for field in (
            "profile", "action", "next_stage"
        )) or definition.get("on_blocked") != expected["on_blocked"] or set(definition["requires"]) != expected["requires"]:
            raise ValueError(f"{contract_name} contract transition is unsupported: {stage}")
    return {"path": path, "version": expected_version, "contract": contract}


def _read_registered_contract(
    knowledge_root: Path, contract_name: str, expected_version: int,
) -> tuple[Path, Path, Dict[str, object]]:
    """Read one registered contract and validate its registry entry and version."""
    contract_label = {
        CONTRACT_NAME: "Inbox reconciliation",
        CURATION_CONTRACT_NAME: "Curation reconciliation",
    }.get(contract_name, contract_name)
    index_path = inbox_contract_path(knowledge_root)
    try:
        index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError("Inbox contract registry is missing") from error
    except yaml.YAMLError as error:
        raise ValueError("Inbox contract registry is invalid YAML") from error
    if not isinstance(index, dict) or index.get("api_version") != REGISTRY_API_VERSION or index.get("kind") != REGISTRY_KIND:
        raise ValueError("Inbox contract registry version is unsupported")
    index_metadata = index.get("metadata")
    if not isinstance(index_metadata, dict) or index_metadata.get("name") != "reconciliation_contract_registry" or index_metadata.get("version") != CONTRACT_VERSION or not isinstance(index_metadata.get("description"), str) or not index_metadata["description"].strip():
        raise ValueError("Inbox contract registry metadata is invalid")
    index_spec = index.get("spec")
    contracts = index_spec.get("contracts") if isinstance(index_spec, dict) else None
    entry = contracts.get(contract_name) if isinstance(contracts, dict) else None
    relative_path = entry.get("path") if isinstance(entry, dict) else None
    if not isinstance(relative_path, str) or not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        raise ValueError("Inbox contract registry entry is invalid")
    path = index_path.parent / relative_path
    try:
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"{contract_label} contract is missing") from error
    except yaml.YAMLError as error:
        raise ValueError(f"{contract_label} contract is invalid YAML") from error
    if not isinstance(contract, dict) or contract.get("api_version") != CONTRACT_API_VERSION or contract.get("kind") != CONTRACT_KIND:
        raise ValueError(f"{contract_label} contract version is unsupported")
    metadata = contract.get("metadata")
    spec = contract.get("spec")
    if not isinstance(metadata, dict) or metadata.get("name") != contract_name or metadata.get("version") != expected_version or not isinstance(metadata.get("description"), str) or not metadata["description"].strip() or not isinstance(spec, dict):
        raise ValueError(f"{contract_label} contract metadata is invalid")
    return index_path, path, spec
