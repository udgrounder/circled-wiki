"""Validated execution contracts for safe Inbox stage reconciliation."""

from pathlib import Path
from typing import Dict

import yaml


CONTRACT_FILENAME = "contracts.yaml"
CONTRACT_NAME = "inbox_reconciliation"
CONTRACT_VERSION = 1
REQUIRED_STAGES = {"pending", "accepted"}
SUPPORTED_TRANSITIONS = {
    "pending": {
        "profile": "inbox-inspection",
        "action": "accept_ready_inbox",
        "next_stage": "accepted",
        "on_blocked": "inbox_review_queue",
        "requires": {
            "required_metadata", "provider_folder", "content_checksum", "sensitivity_review_resolved",
        },
    },
    "accepted": {
        "profile": "evidence-ingest",
        "action": "ingest_accepted",
        "next_stage": "evidence",
        "on_blocked": "inbox_review_queue",
        "requires": {"accepted_inspection", "pii_review_not_blocking"},
    },
}


def inbox_contract_path(knowledge_root: Path) -> Path:
    """Resolve the installed contract, with a source-tree fallback for development."""
    project_root = knowledge_root.resolve().parent
    installed = project_root / ".circled-wiki" / "agent-rules" / CONTRACT_FILENAME
    if installed.is_file():
        return installed
    source_tree = project_root / "agent-rules" / CONTRACT_FILENAME
    if source_tree.is_file():
        return source_tree
    raise ValueError("Inbox reconciliation contract is missing")


def load_inbox_contract(knowledge_root: Path) -> Dict[str, object]:
    """Load only the contract shape required by the Inbox reconciler."""
    path = inbox_contract_path(knowledge_root)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError("Inbox reconciliation contract is invalid YAML") from error
    if not isinstance(data, dict) or data.get("version") != CONTRACT_VERSION:
        raise ValueError("Inbox reconciliation contract version is unsupported")
    contracts = data.get("contracts")
    contract = contracts.get(CONTRACT_NAME) if isinstance(contracts, dict) else None
    stages = contract.get("stages") if isinstance(contract, dict) else None
    if not isinstance(stages, dict) or not REQUIRED_STAGES.issubset(stages):
        raise ValueError("Inbox reconciliation contract has required stages missing")
    for stage in REQUIRED_STAGES:
        definition = stages.get(stage)
        if not isinstance(definition, dict) or not all(
            isinstance(definition.get(field), str) and definition[field]
            for field in ("profile", "action", "next_stage", "on_blocked")
        ) or not isinstance(definition.get("requires"), list):
            raise ValueError(f"Inbox reconciliation contract stage is invalid: {stage}")
        expected = SUPPORTED_TRANSITIONS[stage]
        if any(definition[field] != expected[field] for field in (
            "profile", "action", "next_stage", "on_blocked"
        )) or set(definition["requires"]) != expected["requires"]:
            raise ValueError(f"Inbox reconciliation contract transition is unsupported: {stage}")
    return {"path": path, "version": data["version"], "contract": contract}
